import { describe, expect, test } from "bun:test";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describeResult } from "../src/events.js";
import { loadLatestSavedRun } from "../src/history.js";
import { shouldAutoRefresh } from "../src/refresh.js";
import { SelectionModel, groupByStage, orderedScreeners, parseRegistry } from "../src/registry.js";
import type { Registry } from "../src/types.js";

const ROOT = resolve(dirname(fileURLToPath(new URL(import.meta.url))), "../..");
const registry = parseRegistry(readFileSync(resolve(ROOT, "screeners.json"), "utf-8"));

/** Registry fixture with deliberately non-alphabetical file order inside each stage. */
const SHUFFLED: Registry = {
  version: "test",
  stages: [
    { id: "discovery", name: "Discovery", description: "d" },
    { id: "market-context", name: "Market", description: "m" },
  ],
  screeners: [
    { id: "zeta-screen", name: "Zeta", file: "z.py", stage: "discovery", description: "z", provider: "local", default_enabled: true },
    { id: "alpha-screen", name: "Alpha", file: "a.py", stage: "discovery", description: "a", provider: "local", default_enabled: true },
    { id: "mid-one", name: "Mid One", file: "m.py", stage: "market-context", description: "m", provider: "local", default_enabled: true },
    { id: "off-screen", name: "Off", file: "o.py", stage: "market-context", description: "o", provider: "local", default_enabled: false },
  ],
};

function makeRoot(): string {
  const dir = mkdtempSync(join(tmpdir(), "tui-history-"));
  mkdirSync(join(dir, ".meta-screener", "runs"), { recursive: true });
  return dir;
}

function writeRun(root: string, file: string, record: unknown): void {
  writeFileSync(join(root, ".meta-screener", "runs", file), typeof record === "string" ? record : JSON.stringify(record));
}

describe("registry-order alignment", () => {
  test("orderedScreeners preserves screeners.json order within each stage", () => {
    expect(orderedScreeners(SHUFFLED).map((s) => s.id)).toEqual([
      "zeta-screen",
      "alpha-screen",
      "mid-one",
      "off-screen",
    ]);
  });

  test("groups, flat list, focus, and run order align", () => {
    const flat = orderedScreeners(SHUFFLED);
    const groups = groupByStage(SHUFFLED);
    expect(groups.flatMap((g) => g.screeners.map((s) => s.id))).toEqual(flat.map((s) => s.id));
    const model = SelectionModel.fromRegistry(SHUFFLED);
    expect(model.items.map((s) => s.id)).toEqual(flat.map((s) => s.id));
    expect(model.focused()?.id).toBe(groups[0]!.screeners[0]!.id);
    // Toggle in reverse visible order; run order must still follow workflow order.
    model.clear();
    model.toggle("mid-one");
    model.toggle("alpha-screen");
    model.toggle("zeta-screen");
    expect(model.selectedIds()).toEqual(["zeta-screen", "alpha-screen", "mid-one"]);
  });
});

describe("startup default selection", () => {
  test("preselects only the first default-enabled workflow", () => {
    expect(SelectionModel.fromRegistry(SHUFFLED).selectedIds()).toEqual(["zeta-screen"]);
    expect(SelectionModel.fromRegistry(registry).selectedIds()).toEqual(["meta-overlap"]);
  });

  test("empty selection when no workflow is default-enabled", () => {
    const none: Registry = {
      ...SHUFFLED,
      screeners: SHUFFLED.screeners.map((s) => ({ ...s, default_enabled: false })),
    };
    expect(SelectionModel.fromRegistry(none).selectedIds()).toEqual([]);
  });
});

describe("saved-run loading", () => {
  const VALID = {
    run_id: "run-002",
    started_at: "2026-10-02T10:00:00Z",
    finished_at: "2026-10-02T10:05:00Z",
    status: "ok",
    exit_code: 0,
    screeners: [
      {
        screener_id: "zeta-screen",
        name: "Zeta",
        status: "ok",
        exit_code: 0,
        elapsed_seconds: 12.5,
        summary: "2 picks",
        report_path: "/tmp/z.md",
        top: [
          { rank: 1, ticker: "AAPL", name: "AAPL", detail: "breadth 5" },
          { rank: 2, ticker: "MSFT", name: "Microsoft", detail: "breadth 4" },
        ],
      },
      {
        screener_id: "ghost-screen",
        name: "Ghost",
        status: "ok",
        exit_code: 0,
        elapsed_seconds: 1,
        summary: "unknown workflow",
        report_path: "/tmp/ghost.md",
        top: [],
      },
      {
        screener_id: "alpha-screen",
        name: "Alpha",
        status: "failed",
        exit_code: 1,
        elapsed_seconds: 3,
        summary: "boom",
        report_path: "/tmp/a.md",
        top: [],
        result_error: "boom",
      },
    ],
  };

  test("loads the latest valid record for display without raw output", () => {
    const root = makeRoot();
    writeRun(root, "run-002.json", VALID);
    const loaded = loadLatestSavedRun(root, SHUFFLED);
    expect(loaded?.sourcePath.endsWith("run-002.json")).toBe(true);
    expect(loaded?.record.run_id).toBe("run-002");
    const state = loaded!.state;
    expect(state.runId).toBe("run-002");
    expect(state.running).toBe(false);
    expect(state.overall).toBe("ok");
    expect(state.lastFinishedAt).toBe(Date.parse("2026-10-02T10:05:00Z"));
    // Unknown screener IDs are ignored; known rows map honestly.
    expect(Object.keys(state.byScreener).sort()).toEqual(["alpha-screen", "zeta-screen"]);
    const zeta = state.byScreener["zeta-screen"]!;
    expect(zeta.status).toBe("ok");
    expect(zeta.summary).toBe("2 picks");
    expect(zeta.reportPath).toBe("/tmp/z.md");
    expect(zeta.top).toHaveLength(2);
    expect(zeta.log).toEqual([]);
    expect(state.byScreener["alpha-screen"]!.status).toBe("failed");
  });

  test("ignores malformed records and prefers the latest valid one", () => {
    const root = makeRoot();
    writeRun(root, "run-001.json", VALID);
    writeRun(root, "run-002.json", "this is not json{{{");
    writeRun(root, "run-003.json", { run_id: "run-003", status: "ok" });
    writeRun(root, "run-004.json", { ...VALID, run_id: "run-004", finished_at: "2026-10-03T10:05:00Z" });
    const loaded = loadLatestSavedRun(root, SHUFFLED);
    expect(loaded?.record.run_id).toBe("run-004");
  });

  test("returns null when no valid record exists", () => {
    const root = makeRoot();
    writeRun(root, "bad.json", "[1,2,3]");
    expect(loadLatestSavedRun(root, SHUFFLED)).toBeNull();
    expect(loadLatestSavedRun(join(tmpdir(), "tui-history-missing"), SHUFFLED)).toBeNull();
  });
});

describe("ticker display formatting", () => {
  test("shows the ticker once when name equals ticker", () => {
    const text = describeResult({
      status: "ok",
      log: [],
      top: [{ rank: 1, ticker: "AAPL", name: "AAPL", detail: "breadth 5" }],
    });
    expect(text).toBe("#1 AAPL · breadth 5");
    expect(text).not.toContain("AAPL — AAPL");
  });

  test("shows TICKER — Name when they differ", () => {
    const text = describeResult({
      status: "ok",
      log: [],
      top: [{ rank: 2, ticker: "MSFT", name: "Microsoft", detail: "" }],
    });
    expect(text).toBe("#2 MSFT — Microsoft");
  });
});

describe("selected-only daily refresh", () => {
  const DAY = 24 * 60 * 60 * 1000;
  const NOW = 1_750_000_000_000;

  test("reruns only when the selection is non-empty, due, and idle", () => {
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: NOW - 2 * DAY }, NOW, false, 1)).toBe(true);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: NOW - 2 * DAY }, NOW, false, 0)).toBe(false);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: NOW - 2 * DAY }, NOW, true, 3)).toBe(false);
    expect(shouldAutoRefresh({ enabled: false, lastRunAt: NOW - 2 * DAY }, NOW, false, 3)).toBe(false);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: null }, NOW, false, 3)).toBe(false);
    expect(shouldAutoRefresh({ enabled: true, lastRunAt: NOW - 60_000 }, NOW, false, 3)).toBe(false);
  });
});
