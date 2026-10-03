"""Task 1 RED: registry helpers must import without the optional mcp extra."""

from __future__ import annotations

import importlib
import sys
import unittest


class TestMcpOptional(unittest.TestCase):
    def test_registry_helpers_import_without_mcp(self):
        blocked = {"mcp", "mcp.server", "mcp.client", "mcp.client.stdio"}
        saved = {name: sys.modules.get(name) for name in blocked}
        saved_screener = sys.modules.pop("screener_mcp", None)
        for name in blocked:
            sys.modules[name] = None  # type: ignore[assignment]
        try:
            # Fresh import must succeed without the SDK; helpers must work.
            mod = importlib.import_module("screener_mcp")
            importlib.reload(mod)
            self.assertTrue(hasattr(mod, "read_registry"))
            self.assertTrue(hasattr(mod, "repository_root"))
        finally:
            for name in blocked:
                if saved[name] is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = saved[name]
            sys.modules.pop("screener_mcp", None)
            if saved_screener is not None:
                sys.modules["screener_mcp"] = saved_screener
            import screener_mcp  # noqa: F401  restore normally

    def test_build_server_without_mcp_raises_helpful_error(self):
        # build_server() without the SDK must raise ImportError mentioning the extra.
        import screener_mcp

        has_mcp = True
        try:
            import mcp.server  # noqa: F401
        except ImportError:
            has_mcp = False
        if has_mcp:
            self.skipTest("mcp installed; error path exercised only without extra")
        with self.assertRaises(ImportError) as ctx:
            screener_mcp.build_server()
        self.assertIn("meta-screener-cli[mcp]", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
