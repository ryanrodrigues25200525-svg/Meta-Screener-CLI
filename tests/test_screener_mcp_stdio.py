"""End-to-end stdio integration test for the Meta Screener MCP server.

This launches the real ``screener_mcp`` server in a subprocess over stdio and
drives it with the official MCP Python SDK v2 client. Everything runs against a
``TemporaryDirectory``: ``FINANCE_AI_HOME`` points at the temporary root, the
registered workflows are harmless stdlib stubs, and ``HOME`` is redirected there
as well, so the user's Finance Knowledge Graph and other home data are never
read or written.

The server spawns the real ``meta_screener_cli.py`` runner, which is copied into
the temporary root, so the run path is exercised end to end without Yahoo,
network access, or generated notes.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER = REPO_ROOT / "screener_mcp.py"
CLI = REPO_ROOT / "meta_screener_cli.py"

EXPECTED_TOOLS = {
    "list_screeners",
    "list_checks",
    "plan_screeners",
    "run_screeners",
    "create_screener",
    "register_screener",
    "remove_screener",
}

STUB_META_SCREEN = textwrap.dedent(
    '''
    SCREENS = {}


    def screen(name, category):
        def deco(fn):
            SCREENS[name] = (category, fn)
            return fn
        return deco


    @screen("6m momentum leader (vs SPY)", "momentum")
    def _(c, b):
        return True


    @screen("positive free cash flow", "quality")
    def _(c, b):
        return True
    '''
)

HARMLESS_WORKFLOW = "print('harmless-{name}-ok')\n"


def sample_registry() -> dict[str, Any]:
    """Non-Yahoo stub workflows in two stages.

    The two runnable workflows share the ``discovery`` stage so the CLI's
    inter-stage Yahoo cooldown is never entered, keeping the run deterministic
    and fast; ``context-local`` exists only to exercise stage-ordered planning.
    """
    return {
        "version": "0.3.0",
        "stages": [
            {"id": "discovery", "name": "Candidate discovery"},
            {"id": "market-context", "name": "Market and factor context"},
        ],
        "screeners": [
            {
                "id": "alpha-local",
                "name": "Alpha Local",
                "file": "harmless_alpha.py",
                "stage": "discovery",
                "description": "Harmless alpha stub.",
                "provider": "Local stub",
                "yahoo": False,
                "requirements": [],
                "reads": [],
                "writes": [],
                "default_enabled": True,
                "args": [],
            },
            {
                "id": "beta-local",
                "name": "Beta Local",
                "file": "harmless_beta.py",
                "stage": "discovery",
                "description": "Harmless beta stub.",
                "provider": "Local stub",
                "yahoo": False,
                "requirements": [],
                "reads": [],
                "writes": [],
                "default_enabled": True,
                "args": [],
            },
            {
                "id": "context-local",
                "name": "Context Local",
                "file": "harmless_context.py",
                "stage": "market-context",
                "description": "Harmless context stub.",
                "provider": "Local stub",
                "yahoo": False,
                "requirements": [],
                "reads": [],
                "writes": [],
                "default_enabled": True,
                "args": [],
            },
        ],
    }


class ScreenerMcpStdioIntegrationTests(unittest.TestCase):
    def test_stdio_server_end_to_end(self) -> None:
        asyncio.run(self._scenario())

    async def _scenario(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            home = root / "home"
            home.mkdir()
            self._build_root(root)

            env = {**os.environ, "FINANCE_AI_HOME": str(root), "HOME": str(home)}
            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SERVER)],
                env=env,
                cwd=str(REPO_ROOT),
            )

            async with Client(params) as client:
                # 1. Tool discovery.
                listing = await client.list_tools()
                self.assertEqual({tool.name for tool in listing.tools}, EXPECTED_TOOLS)

                # 2. List and plan against the isolated registry.
                listed = await self._call(client, "list_screeners", {})
                self.assertEqual(
                    [stage["id"] for stage in listed["stages"]],
                    ["discovery", "market-context"],
                )
                self.assertEqual(
                    [item["id"] for item in listed["stages"][0]["screeners"]],
                    ["alpha-local", "beta-local"],
                )

                checks = await self._call(client, "list_checks", {})
                self.assertEqual(checks["count"], 2)

                plan = await self._call(
                    client,
                    "plan_screeners",
                    {"screener_ids": ["context-local", "beta-local", "alpha-local"]},
                )
                self.assertEqual(
                    plan["ordered_ids"], ["alpha-local", "beta-local", "context-local"]
                )
                self.assertEqual(plan["command"][2:4], ["run", "--json-events"])

                # 3. Profile creation and workflow registration through the tools.
                created = await self._call(
                    client,
                    "create_screener",
                    {
                        "screener_id": "custom-profile",
                        "name": "Custom Profile",
                        "checks": ["positive free cash flow"],
                    },
                )
                self.assertEqual(
                    created["created"]["args"], ["--check", "positive free cash flow"]
                )
                registered = await self._call(
                    client,
                    "register_screener",
                    {
                        "screener_id": "gamma-local",
                        "name": "Gamma Local",
                        "file": "harmless_alpha.py",
                        "stage": "discovery",
                    },
                )
                self.assertEqual(registered["registered"]["id"], "gamma-local")
                self.assertTrue(Path(registered["resolved_file"]).is_file())

                stored = self._registry(root)["screeners"]
                stored_ids = {item["id"] for item in stored}
                self.assertTrue({"custom-profile", "gamma-local"} <= stored_ids)

                # 4. Run two harmless sample workflows through the real CLI.
                run = await self._call(
                    client,
                    "run_screeners",
                    {"screener_ids": ["alpha-local", "beta-local"]},
                )
                self.assertTrue(run["ok"], run)
                self.assertEqual(run["returncode"], 0)
                self.assertFalse(run["rate_limited"])
                self.assertEqual(run["screeners"], ["alpha-local", "beta-local"])

                event_types = [event.get("type") for event in run["events"]]
                self.assertEqual(event_types.count("screener_finished"), 2)
                self.assertIn("run_started", event_types)
                self.assertIn("run_finished", event_types)
                finished = [
                    event for event in run["events"] if event.get("type") == "screener_finished"
                ]
                self.assertTrue(all(event["status"] == "ok" for event in finished), finished)
                output_lines = {
                    event.get("line")
                    for event in run["events"]
                    if event.get("type") == "output_line"
                }
                self.assertIn("harmless-alpha-ok", output_lines)
                self.assertIn("harmless-beta-ok", output_lines)

                # 5. Removal unregisters without deleting the source file.
                removed = await self._call(
                    client, "remove_screener", {"screener_id": "gamma-local"}
                )
                self.assertEqual(removed["removed"]["id"], "gamma-local")
                self.assertFalse(removed["source_deleted"])
                self.assertTrue((root / "harmless_alpha.py").is_file())
                remaining = {item["id"] for item in self._registry(root)["screeners"]}
                self.assertNotIn("gamma-local", remaining)

            # The redirected HOME stayed untouched (no Finance Knowledge Graph, no writes).
            self.assertEqual(list(home.iterdir()), [])

    def _build_root(self, root: Path) -> None:
        shutil.copy2(CLI, root / "meta_screener_cli.py")
        (root / "meta_screen.py").write_text(STUB_META_SCREEN, encoding="utf-8")
        (root / "harmless_alpha.py").write_text(
            HARMLESS_WORKFLOW.format(name="alpha"), encoding="utf-8"
        )
        (root / "harmless_beta.py").write_text(
            HARMLESS_WORKFLOW.format(name="beta"), encoding="utf-8"
        )
        (root / "harmless_context.py").write_text(
            HARMLESS_WORKFLOW.format(name="context"), encoding="utf-8"
        )
        (root / "screeners.json").write_text(
            json.dumps(sample_registry(), indent=2) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _registry(root: Path) -> dict[str, Any]:
        return json.loads((root / "screeners.json").read_text(encoding="utf-8"))

    async def _call(self, client: Client, name: str, arguments: dict[str, Any]) -> Any:
        result = await client.call_tool(name, arguments)
        self.assertFalse(result.is_error, f"{name} failed: {result}")
        if result.structured_content is not None:
            return result.structured_content
        for item in result.content:
            text = getattr(item, "text", None)
            if text:
                return json.loads(text)
        raise AssertionError(f"{name} returned no structured content")


if __name__ == "__main__":
    unittest.main()
