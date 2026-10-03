import { describe, expect, test } from "bun:test";
import { SelectionModel, defaultEnabledIds, groupByStage, orderedScreeners, parseRegistry } from "../src/registry.js";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(new URL(import.meta.url))), "../..");
const registry = parseRegistry(readFileSync(resolve(ROOT, "screeners.json"), "utf-8"));

describe("workflow selection", () => {
  test("registry exposes 24 workflows", () => {
    expect(registry.screeners).toHaveLength(24);
  });

  test("screen-history is the only default-disabled workflow", () => {
    const disabled = registry.screeners.filter((s) => s.default_enabled === false).map((s) => s.id);
    expect(disabled).toEqual(["screen-history"]);
    expect(defaultEnabledIds(registry)).toHaveLength(23);
  });

  test("groups preserve the six registry stages", () => {
    const groups = groupByStage(registry);
    expect(groups.map((g) => g.id)).toEqual(["discovery", "meta-signals", "market-context", "company-signals", "events", "tracking"]);
    expect(groups.reduce((n, g) => n + g.screeners.length, 0)).toBe(24);
  });

  test("selection preselects only the first default and wraps navigation", () => {
    const model = SelectionModel.fromRegistry(registry);
    expect(model.selectedIds()).toEqual(["fundamental-rotation"]);
    expect(model.selected.has("screen-history")).toBe(false);
    model.moveTo(0);
    model.move(-1);
    expect(model.focusedIndex).toBe(orderedScreeners(registry).length - 1);
    model.move(1);
    expect(model.focusedIndex).toBe(0);
  });

  test("toggle/select-all/clear keep stage order for runs", () => {
    const model = SelectionModel.fromRegistry(registry);
    model.clear();
    expect(model.selectedIds()).toEqual([]);
    model.toggle("fundamental-rotation");
    model.toggle("sector-rotation");
    // Stage order: discovery before market-context regardless of toggle order.
    model.clear();
    model.toggle("sector-rotation");
    model.toggle("meta-momentum");
    expect(model.selectedIds()).toEqual(["meta-momentum", "sector-rotation"]);
    model.selectAll();
    expect(model.count()).toBe(24);
    model.selectDefaults();
    expect(model.count()).toBe(23);
  });

  test("unknown ids are ignored", () => {
    const model = SelectionModel.fromRegistry(registry);
    const before = model.count();
    model.toggle("no-such-screener");
    expect(model.count()).toBe(before);
  });
});
