import { describe, expect, test } from "bun:test";
import { detailText, navText, statusText } from "../src/app.js";
import { renderDashboardText } from "../src/layout.js";
import { blankRunState } from "../src/events.js";
import { shouldAutoRefresh } from "../src/refresh.js";
import { groupByStage, loadRegistryFile, orderedScreeners, SelectionModel } from "../src/registry.js";
import { buildRunnerCommand, layoutForWidth, resolveRuntime } from "../src/runtime.js";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(new URL(import.meta.url))), "../..");
const registry = loadRegistryFile(resolve(ROOT, "screeners.json"));

describe("narrow-terminal state/layout", () => {
  test("layout breakpoint splits at 80 columns", () => {
    expect(layoutForWidth(79)).toBe("narrow");
    expect(layoutForWidth(80)).toBe("normal");
    expect(layoutForWidth(120)).toBe("normal");
  });

  test("normal and narrow snapshots differ and stay readable", () => {
    const groups = groupByStage(registry);
    const flat = orderedScreeners(registry);
    const selection = SelectionModel.fromRegistry(registry);
    const base = {
      groups, flat, focusedIndex: 0, selected: selection.selected,
      run: blankRunState(), showDetails: true, refreshEnabled: false, overall: "idle",
    };
    const normal = renderDashboardText(base, { width: 110, height: 32 });
    const narrow = renderDashboardText(base, { width: 60, height: 32 });
    expect(normal).toContain("## Candidate discovery");
    expect(normal).toContain("↑/↓ move");
    expect(narrow).not.toContain("## Candidate discovery");
    expect(narrow).toContain("focus 1/17");
    for (const line of narrow.split("\n")) {
      expect(line.length).toBeLessThanOrEqual(60);
    }
  });

  test("nav/detail/status text helpers expose selection and results", () => {
    const selection = SelectionModel.fromRegistry(registry);
    const run = blankRunState();
    const groups = groupByStage(registry);
    expect(navText(selection, run, groups)).toContain("meta-overlap");
    expect(detailText(selection, run, false)).toContain(selection.focused()?.name ?? "");
    expect(statusText(selection, run, { enabled: false, lastRunAt: null })).toContain("selected 16");
  });
});

describe("runner command + refresh", () => {
  test("runner argv uses repeated --screener without a shell string", () => {
    expect(buildRunnerCommand("/usr/bin/python3", "/repo", ["a", "b"])).toEqual([
      "/usr/bin/python3",
      "/repo/meta_screener_cli.py",
      "run",
      "--json-events",
      "--screener",
      "a",
      "--screener",
      "b",
    ]);
  });

  test("runtime resolves launcher env with sane fallbacks", () => {
    const fromEnv = resolveRuntime({ META_SCREENER_ROOT: "/r", META_SCREENER_PYTHON: "/p" }, "/r/tui");
    expect(fromEnv).toEqual({ root: "/r", python: "/p" });
    const fallback = resolveRuntime({}, "/r/tui");
    expect(fallback).toEqual({ root: "/r", python: "python3" });
  });

  test("foreground daily refresh is opt-in with no catch-up burst", () => {
    const now = 1_700_000_000_000;
    const day = 24 * 60 * 60 * 1000;
    expect(shouldAutoRefresh({ enabled: false, lastRunAt: now - 2 * day }, now, false)).toBe(false);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: null }, now, false)).toBe(false);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: now - 2 * day }, now, false)).toBe(true);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: now - 2 * day }, now, true)).toBe(false);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: now - 60_000 }, now, false)).toBe(false);
  });
});
