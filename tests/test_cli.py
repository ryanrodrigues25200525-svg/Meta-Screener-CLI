"""Tests for Meta Screener CLI selection, JSON Lines runs, and saved results."""

import argparse
import io
import json
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import meta_screener_cli as cli


def one_screener_registry():
    return {
        "stages": [{"id": "discovery", "name": "Discovery"}],
        "screeners": [
            {
                "id": "demo",
                "name": "Demo",
                "file": "meta_screen.py",
                "stage": "discovery",
                "description": "Demo workflow",
                "provider": "local",
                "yahoo": False,
                "default_enabled": True,
                "args": [],
            }
        ],
    }


class SelectionTests(unittest.TestCase):
    def test_repeated_screener_ids_are_selected_in_registry_stage_order(self):
        args = cli.build_parser().parse_args(
            ["run", "--screener", "sector-rotation", "--screener", "meta-overlap"]
        )

        selected = cli.select_screeners(cli.read_registry(), args)

        self.assertEqual([item["id"] for item in selected], ["meta-overlap", "sector-rotation"])

    def test_no_arguments_launches_the_tui_instead_of_running_a_screener(self):
        with patch.object(cli, "launch_tui", create=True, return_value=0) as launch, \
             patch.object(cli, "run_command", return_value=0) as run_command:
            result = cli.main([])

        self.assertEqual(result, 0)
        launch.assert_called_once_with()
        run_command.assert_not_called()

    def test_tui_launcher_runs_the_package_start_script_with_repo_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            tui_dir = root / "tui"
            (tui_dir / "node_modules").mkdir(parents=True)
            (tui_dir / "package.json").write_text("{}", encoding="utf-8")
            with patch.object(cli, "ROOT", root), \
                 patch.object(cli.shutil, "which", return_value="/usr/bin/bun"), \
                 patch.object(cli.subprocess, "call", return_value=0) as start:
                result = cli.launch_tui()

        self.assertEqual(result, 0)
        command = start.call_args.args[0]
        self.assertEqual(command, ["/usr/bin/bun", "run", "start"])
        self.assertEqual(start.call_args.kwargs["cwd"], tui_dir)
        self.assertEqual(start.call_args.kwargs["env"]["META_SCREENER_ROOT"], str(root))
        self.assertEqual(start.call_args.kwargs["env"]["META_SCREENER_PYTHON"], sys.executable)


class JsonEventTests(unittest.TestCase):
    def test_child_output_is_emitted_as_an_event_without_polluting_stdout(self):
        events = []
        stdout = io.StringIO()

        with redirect_stdout(stdout):
            result = cli.run_process(
                [sys.executable, "-c", "print('worker line')"],
                event_sink=events.append,
                run_id="run-1",
                screener_id="demo",
            )

        self.assertEqual(result, (0, False))
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(events[0]["type"], "output_line")
        self.assertEqual(events[0]["run_id"], "run-1")
        self.assertEqual(events[0]["screener_id"], "demo")
        self.assertEqual(events[0]["line"], "worker line")

    def test_rate_limit_output_terminates_child_without_retry(self):
        events = []

        result = cli.run_process(
            [sys.executable, "-c", "import time; print('HTTPError 429', flush=True); time.sleep(5)"],
            event_sink=events.append,
            run_id="run-429",
            screener_id="demo",
        )

        self.assertTrue(result[1])
        self.assertNotEqual(result[0], 0)
        self.assertEqual(events[0]["line"], "HTTPError 429")

    def test_child_output_is_streamed_before_process_exit(self):
        received = threading.Event()
        events = []

        def capture(event):
            events.append(event)
            if event.get("type") == "output_line":
                received.set()

        worker = threading.Thread(target=lambda: cli.run_process(
            [sys.executable, "-c", "import time; print('early line'); time.sleep(1.2)"],
            event_sink=capture,
            run_id="run-stream",
            screener_id="demo",
        ))
        worker.start()
        try:
            self.assertTrue(received.wait(timeout=0.5), "child stdout did not stream before process exit")
        finally:
            worker.join(timeout=2)

        self.assertFalse(worker.is_alive())
        self.assertEqual(events[0]["line"], "early line")

    def test_json_run_emits_parseable_events_and_persists_a_compact_record(self):
        args = argparse.Namespace(
            all=False,
            stage=None,
            screener=["demo"],
            gap_seconds=10,
            workers=1,
            batch_size=25,
            python=sys.executable,
            continue_on_error=False,
            json_events=True,
        )
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temp_dir:
            runs_dir = Path(temp_dir) / "runs"
            registry = one_screener_registry()
            registry["screeners"][0]["file"] = "workflow.py"
            with patch.object(cli, "command_for", return_value=[sys.executable, "-c", "print('ready')"]), \
                 patch.object(cli, "RUNS_DIR", runs_dir), \
                 redirect_stdout(stdout):
                result = cli.run_command(registry, args)

            events = [json.loads(line) for line in stdout.getvalue().splitlines()]
            self.assertEqual(result, 0)
            self.assertEqual(
                [event["type"] for event in events],
                ["run_started", "screener_started", "output_line", "screener_finished", "run_finished"],
            )
            self.assertTrue(all(event["run_id"] == events[0]["run_id"] for event in events))
            self.assertNotIn("\nready\n", "\n" + stdout.getvalue())
            record = json.loads(next(runs_dir.glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(record["run_id"], events[0]["run_id"])
            self.assertEqual(record["screeners"][0]["status"], "ok")

    def test_result_error_respects_continue_on_error(self):
        def two_screener_registry():
            reg = one_screener_registry()
            second = dict(reg["screeners"][0])
            second["id"] = "second"
            second["name"] = "Second"
            reg["screeners"].append(second)
            return reg

        args = argparse.Namespace(
            all=False,
            stage=None,
            screener=["demo", "second"],
            gap_seconds=10,
            workers=1,
            batch_size=25,
            python=sys.executable,
            continue_on_error=True,
            json_events=True,
        )
        stdout = io.StringIO()
        registry = two_screener_registry()
        calls = {"reads": 0}

        def fake_read(_path):
            calls["reads"] += 1
            if calls["reads"] == 1:
                return {"summary": None, "report_path": None, "top": None,
                        "result_error": "missing result json"}
            return {"summary": "ok", "report_path": None, "top": None, "result_error": None}

        with tempfile.TemporaryDirectory() as temp_dir:
            runs_dir = Path(temp_dir) / "runs"
            with patch.object(cli, "command_for", return_value=["true"]), \
                 patch.object(cli, "run_process", return_value=(0, False)), \
                 patch.object(cli, "read_result_artifact", side_effect=fake_read), \
                 patch.object(cli, "RUNS_DIR", runs_dir), \
                 patch.object(cli.time, "sleep", return_value=None), \
                 redirect_stdout(stdout):
                cli.run_command(registry, args)

            events = [json.loads(line) for line in stdout.getvalue().splitlines()]
            finished = [e for e in events if e["type"] == "screener_finished"]
            self.assertEqual([e["screener_id"] for e in finished], ["demo", "second"])


class ResultTests(unittest.TestCase):
    def test_result_artifact_normalizes_ranked_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "results.json"
            result_path.write_text(json.dumps({
                "summary": "Two names passed",
                "report_path": "report.md",
                "top": [{"rank": 1, "ticker": "ABC", "name": "Alpha", "detail": "3 signals"}],
            }), encoding="utf-8")

            result = cli.read_result_artifact(result_path)

        self.assertEqual(result["summary"], "Two names passed")
        self.assertEqual(result["top"], [{"rank": 1, "ticker": "ABC", "name": "Alpha", "detail": "3 signals"}])
        self.assertEqual(result["result_error"], None)

    def test_result_artifact_rejects_invalid_ranked_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "results.json"
            result_path.write_text(json.dumps({"top": [{"rank": 1, "name": "Missing ticker"}]}),
                                   encoding="utf-8")

            result = cli.read_result_artifact(result_path)

        self.assertEqual(result["top"], [])
        self.assertIn("ticker is required", result["result_error"])

    def test_ranked_workflow_recognizes_dot_slash_registry_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            result_dir = root / "results"
            (root / "rotation_screen.py").write_text("# workflow\n", encoding="utf-8")
            screener = {"id": "rotation", "file": "./rotation_screen.py", "args": [], "yahoo": False}

            with patch.object(cli, "ROOT", root):
                command = cli.command_for(screener, "python", 1, 8, 15, result_dir)
                artifact = cli.result_artifact_for(screener, result_dir)

        self.assertEqual(command[-4:], [
            "--csv-out", str(result_dir / "rotation.csv"),
            "--result-json", str(result_dir / "rotation.json"),
        ])
        self.assertEqual(artifact, result_dir / "rotation.json")

    def test_custom_profile_arguments_are_passed_without_shell_joining(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            (root / "meta_screen.py").write_text("# screen entry\n", encoding="utf-8")
            screener = {
                "id": "custom-growth",
                "file": "meta_screen.py",
                "args": ["--check", "high revenue growth (>20%)", "--check", "cash-backed earnings"],
                "yahoo": True,
            }
            with patch.object(cli, "ROOT", root):
                command = cli.command_for(screener, "python", 1, 25, 10)

        self.assertEqual(command[:8], [
            "python", str(root / "meta_screen.py"), "--check", "high revenue growth (>20%)",
            "--check", "cash-backed earnings", "--workers", "1",
        ])
        self.assertEqual(command[-4:], ["--batch-size", "25", "--batch-pause-seconds", "10"])


class IdValidationTests(unittest.TestCase):
    def _assert_id_validity(self, sid, ok):
        import json as _json

        reg = one_screener_registry()
        reg["screeners"][0]["id"] = sid
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "screeners.json"
            path.write_text(_json.dumps(reg), encoding="utf-8")
            with patch.object(cli, "REGISTRY_PATH", path):
                if ok:
                    cli.read_registry()
                else:
                    with self.assertRaises(ValueError):
                        cli.read_registry()

    def test_rejects_leading_digit_and_double_hyphen_ids(self):
        for bad in ("1abc", "a--b", "abc-"):
            with self.subTest(bad=bad):
                self._assert_id_validity(bad, False)

    def test_accepts_strict_ids(self):
        for good in ("a1-b2", "meta-overlap", "abc"):
            with self.subTest(good=good):
                self._assert_id_validity(good, True)

    def test_plan_mentions_result_wiring(self):
        registry = one_screener_registry()
        registry["screeners"][0].update({"id": "meta-overlap", "yahoo": True})
        args = cli.build_parser().parse_args(
            ["plan", "--screener", "meta-overlap"]
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.plan_command(registry, args)
        out = buf.getvalue()
        self.assertTrue(
            "--result-json" in out or "json" in out.lower() and "result" in out.lower(),
            f"plan output should mention result wiring:\n{out}",
        )


if __name__ == "__main__":
    unittest.main()
