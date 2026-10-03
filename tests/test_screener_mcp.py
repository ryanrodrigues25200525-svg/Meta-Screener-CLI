"""Focused tests for the stdio MCP screener registry tools.

The tests use an isolated temporary registry and a mocked subprocess so no
Yahoo-backed screener is ever launched.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import screener_mcp


STUB_META_SCREEN = '''
SCREENS = {}


def screen(name, category):
    def deco(fn):
        SCREENS[name] = (category, fn)
        return fn
    return deco


@screen("6m momentum leader (vs SPY)", "momentum")
def _(c, b):
    return True


@screen("dip within uptrend", "momentum")
def _(c, b):
    return True


@screen("positive free cash flow", "quality")
def _(c, b):
    return True
'''


def sample_registry() -> dict:
    return {
        "version": "0.2.0",
        "stages": [
            {"id": "discovery", "name": "Candidate discovery"},
            {"id": "market-context", "name": "Market and factor context"},
        ],
        "screeners": [
            {
                "id": "meta-overlap",
                "name": "Meta Screen: Cross-Signal Breadth",
                "file": "meta_screen.py",
                "stage": "discovery",
                "description": "Cross-signal breadth.",
                "provider": "Yahoo Finance via yfinance",
                "yahoo": True,
                "requirements": ["yfinance", "pandas", "numpy"],
                "reads": [],
                "writes": [],
                "default_enabled": True,
                "args": [],
            },
            {
                "id": "second-screen",
                "name": "Second Screen",
                "file": "workflow.py",
                "stage": "market-context",
                "description": "A repository workflow.",
                "provider": "Local data",
                "yahoo": False,
                "requirements": [],
                "reads": [],
                "writes": [],
                "default_enabled": True,
                "args": [],
            },
        ],
    }


class FakeProcess:
    """Minimal subprocess.Popen stand-in for run delegation tests."""

    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = iter(lines)
        self._returncode = returncode
        self.terminated = False

    def poll(self) -> None:
        return None

    def wait(self) -> int:
        return self._returncode

    def terminate(self) -> None:
        self.terminated = True


class RegistryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "meta_screen.py").write_text(STUB_META_SCREEN, encoding="utf-8")
        (self.root / "meta_screener_cli.py").write_text("# runner stub\n", encoding="utf-8")
        (self.root / "workflow.py").write_text("# workflow\n", encoding="utf-8")
        screener_mcp.write_registry(self.root, sample_registry())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def registry(self) -> dict:
        return json.loads((self.root / "screeners.json").read_text(encoding="utf-8"))


class ListAndPlanTests(RegistryTestCase):
    def test_list_screeners_groups_by_stage(self) -> None:
        result = screener_mcp._list_screeners(self.root)
        stage_ids = [stage["id"] for stage in result["stages"]]
        self.assertEqual(stage_ids, ["discovery", "market-context"])
        self.assertEqual(result["stages"][0]["screeners"][0]["id"], "meta-overlap")

    def test_list_checks_parses_meta_screen(self) -> None:
        result = screener_mcp._list_checks(self.root)
        names = {check["name"] for check in result["checks"]}
        self.assertEqual(result["count"], 3)
        self.assertIn("6m momentum leader (vs SPY)", names)
        self.assertIn("positive free cash flow", names)

    def test_plan_orders_by_stage_and_builds_command(self) -> None:
        result = screener_mcp._plan_screeners(self.root, ["second-screen", "meta-overlap"])
        self.assertEqual(result["ordered_ids"], ["meta-overlap", "second-screen"])
        self.assertEqual(result["command"][0], sys.executable)
        self.assertEqual(result["command"][2:4], ["run", "--json-events"])
        self.assertEqual(result["command"].count("--screener"), 2)

    def test_plan_command_matches_stage_order(self) -> None:
        result = screener_mcp._plan_screeners(self.root, ["second-screen", "meta-overlap"])
        command_ids = [
            result["command"][index + 1]
            for index, token in enumerate(result["command"])
            if token == "--screener"
        ]
        self.assertEqual(result["ordered_ids"], ["meta-overlap", "second-screen"])
        self.assertEqual(command_ids, result["ordered_ids"])

    def test_plan_rejects_unknown_screener(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._plan_screeners(self.root, ["does-not-exist"])


class RunDelegationTests(RegistryTestCase):
    def test_run_builds_argument_vector(self) -> None:
        lines = ['{"event": "run_started", "run_id": "r1"}\n', '{"event": "run_finished", "run_id": "r1"}\n']
        with mock.patch.object(screener_mcp, "Popen") as popen:
            popen.return_value = FakeProcess(lines)
            result = screener_mcp._run_screeners(self.root, ["meta-overlap"])

        command = popen.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertEqual(command[1], str(self.root / "meta_screener_cli.py"))
        self.assertEqual(command[2:6], ["run", "--json-events", "--screener", "meta-overlap"])
        self.assertNotIn("shell", popen.call_args.kwargs)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["events"]), 2)

    def test_run_repeats_screener_flag_and_orders_by_stage(self) -> None:
        with mock.patch.object(screener_mcp, "Popen") as popen:
            popen.return_value = FakeProcess([])
            result = screener_mcp._run_screeners(self.root, ["second-screen", "meta-overlap"])

        command = popen.call_args.args[0]
        self.assertEqual(command.count("--screener"), 2)
        self.assertEqual(result["screeners"], ["meta-overlap", "second-screen"])
        overlap_index = command.index("meta-overlap")
        second_index = command.index("second-screen")
        self.assertLess(overlap_index, second_index)
        # Every --screener is immediately followed by its id.
        for index, token in enumerate(command):
            if token == "--screener":
                self.assertIn(command[index + 1], {"meta-overlap", "second-screen"})

    def test_run_detects_rate_limit_and_stops(self) -> None:
        lines = ['{"event": "output_line", "line": "YFRateLimitError: too many requests"}\n']
        with mock.patch.object(screener_mcp, "Popen") as popen:
            process = FakeProcess(lines, returncode=2)
            popen.return_value = process
            result = screener_mcp._run_screeners(self.root, ["meta-overlap"])

        self.assertTrue(result["rate_limited"])
        self.assertFalse(result["ok"])
        self.assertTrue(process.terminated)

    def test_run_rejects_unknown_before_launch(self) -> None:
        with mock.patch.object(screener_mcp, "Popen") as popen:
            with self.assertRaises(ValueError):
                screener_mcp._run_screeners(self.root, ["nope"])
        popen.assert_not_called()


class CreateScreenerTests(RegistryTestCase):
    def test_create_writes_custom_profile(self) -> None:
        result = screener_mcp._create_screener(
            self.root,
            "my-value-profile",
            "My Value Profile",
            ["6m momentum leader (vs SPY)", "positive free cash flow"],
        )
        entry = result["created"]
        self.assertEqual(entry["file"], "meta_screen.py")
        self.assertEqual(entry["stage"], "discovery")
        self.assertIs(entry["yahoo"], True)
        self.assertIs(entry["default_enabled"], False)
        self.assertEqual(
            entry["args"],
            ["--check", "6m momentum leader (vs SPY)", "--check", "positive free cash flow"],
        )
        stored = {item["id"]: item for item in self.registry()["screeners"]}
        self.assertIn("my-value-profile", stored)

    def test_create_rejects_duplicate_id(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._create_screener(self.root, "meta-overlap", "Dup", ["positive free cash flow"])

    def test_create_rejects_unsafe_id(self) -> None:
        for bad_id in ["Bad_ID", "UPPER", "1leading", "double--hyphen", "trailing-"]:
            with self.subTest(bad_id=bad_id), self.assertRaises(ValueError):
                screener_mcp._create_screener(self.root, bad_id, "Bad", ["positive free cash flow"])

    def test_create_rejects_unknown_check(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._create_screener(self.root, "bad-check-profile", "Bad", ["not a real check"])

    def test_create_rejects_empty_and_duplicate_checks(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._create_screener(self.root, "empty-profile", "Empty", [])
        with self.assertRaises(ValueError):
            screener_mcp._create_screener(
                self.root,
                "dup-check-profile",
                "Dup",
                ["positive free cash flow", "positive free cash flow"],
            )


class RegisterScreenerTests(RegistryTestCase):
    def test_register_accepts_repo_python_file(self) -> None:
        result = screener_mcp._register_screener(
            self.root,
            "workflow-screen",
            "Workflow Screen",
            "workflow.py",
            "market-context",
            args=["--dry"],
            requirements=["pandas"],
        )
        entry = result["registered"]
        self.assertEqual(entry["file"], "workflow.py")
        self.assertEqual(entry["args"], ["--dry"])
        self.assertEqual(entry["requirements"], ["pandas"])
        self.assertTrue(Path(result["resolved_file"]).is_file())
        stored = {item["id"]: item for item in self.registry()["screeners"]}
        self.assertIn("workflow-screen", stored)

    def test_register_rejects_missing_file(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._register_screener(self.root, "missing", "Missing", "nope.py", "discovery")

    def test_register_rejects_non_python_file(self) -> None:
        (self.root / "notes.txt").write_text("hi\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            screener_mcp._register_screener(self.root, "notes", "Notes", "notes.txt", "discovery")

    def test_register_rejects_absolute_and_escaping_paths(self) -> None:
        outside = self.root.parent / "outside.py"
        outside.write_text("# outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        with self.assertRaises(ValueError):
            screener_mcp._register_screener(self.root, "absolute", "Abs", str(outside), "discovery")
        with self.assertRaises(ValueError):
            screener_mcp._register_screener(self.root, "escape", "Escape", "../outside.py", "discovery")

    def test_register_rejects_symlink_escape(self) -> None:
        outside = self.root.parent / "symlink-target.py"
        outside.write_text("# outside\n", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        link = self.root / "linked.py"
        link.symlink_to(outside)
        self.addCleanup(link.unlink, missing_ok=True)
        with self.assertRaises(ValueError):
            screener_mcp._register_screener(self.root, "linked", "Linked", "linked.py", "discovery")

    def test_register_rejects_unknown_stage(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._register_screener(self.root, "wf", "WF", "workflow.py", "not-a-stage")

    def test_register_rejects_non_string_argument_list(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._register_screener(self.root, "wf", "WF", "workflow.py", "discovery", args=[1, 2])


class RemoveScreenerTests(RegistryTestCase):
    def test_remove_unregisters_without_deleting_source(self) -> None:
        result = screener_mcp._remove_screener(self.root, "second-screen")
        self.assertIs(result["source_deleted"], False)
        self.assertTrue((self.root / "workflow.py").is_file())
        stored = {item["id"] for item in self.registry()["screeners"]}
        self.assertNotIn("second-screen", stored)

    def test_remove_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            screener_mcp._remove_screener(self.root, "not-registered")


class AtomicWriteTests(RegistryTestCase):
    def test_registry_write_leaves_no_temp_files(self) -> None:
        screener_mcp._create_screener(self.root, "atomic-profile", "Atomic", ["positive free cash flow"])
        leftovers = list(self.root.glob(".*.tmp"))
        self.assertEqual(leftovers, [])
        json.loads((self.root / "screeners.json").read_text(encoding="utf-8"))


class ServerSurfaceTests(unittest.TestCase):
    @unittest.skipUnless(
        __import__("importlib").util.find_spec("mcp") is not None,
        "requires optional mcp extra: pip install 'meta-screener-cli[mcp]'",
    )
    def test_server_exposes_required_tools(self) -> None:
        server = screener_mcp.build_server()
        tools = asyncio.run(server.list_tools())
        names = {tool.name for tool in tools}
        self.assertEqual(
            names,
            {
                "list_screeners",
                "list_checks",
                "plan_screeners",
                "run_screeners",
                "create_screener",
                "register_screener",
                "remove_screener",
            },
        )


if __name__ == "__main__":
    unittest.main()
