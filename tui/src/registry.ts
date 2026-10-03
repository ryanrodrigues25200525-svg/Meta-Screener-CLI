import { readFileSync } from "node:fs";
import type { Registry, ScreenerMeta } from "./types.js";

export interface GroupedStage {
  id: string;
  name: string;
  description: string;
  screeners: ScreenerMeta[];
}

export function loadRegistryFile(path: string): Registry {
  return parseRegistry(readFileSync(path, "utf-8"));
}

export function parseRegistry(text: string): Registry {
  const data = JSON.parse(text) as Registry;
  if (!Array.isArray(data.stages) || !Array.isArray(data.screeners)) {
    throw new Error("screeners.json must contain 'stages' and 'screeners' lists");
  }
  return data;
}

/** Screeners in registry stage order, preserving screeners.json file order within each stage. */
export function orderedScreeners(registry: Registry): ScreenerMeta[] {
  const order = new Map(registry.stages.map((s, i) => [s.id, i]));
  return registry.screeners
    .map((screener, index) => ({ screener, index }))
    .sort((a, b) => {
      const oa = order.get(a.screener.stage) ?? Number.MAX_SAFE_INTEGER;
      const ob = order.get(b.screener.stage) ?? Number.MAX_SAFE_INTEGER;
      if (oa !== ob) return oa - ob;
      return a.index - b.index;
    })
    .map((entry) => entry.screener);
}

export function groupByStage(registry: Registry): GroupedStage[] {
  return registry.stages.map((stage) => ({
    id: stage.id,
    name: stage.name,
    description: stage.description,
    screeners: registry.screeners.filter((s) => s.stage === stage.id),
  }));
}

export function defaultEnabledIds(registry: Registry): string[] {
  return orderedScreeners(registry)
    .filter((s) => s.default_enabled !== false)
    .map((s) => s.id);
}

export class SelectionModel {
  readonly items: ScreenerMeta[];
  focusedIndex = 0;
  readonly selected = new Set<string>();

  constructor(items: ScreenerMeta[], preselect?: Iterable<string>) {
    this.items = items;
    if (preselect) {
      for (const id of preselect) this.selected.add(id);
    }
  }

  /** Startup selection: only the first default-enabled workflow. Run-all stays separate. */
  static fromRegistry(registry: Registry): SelectionModel {
    const items = orderedScreeners(registry);
    const first = items.find((s) => s.default_enabled !== false);
    return new SelectionModel(items, first ? [first.id] : []);
  }

  focused(): ScreenerMeta | undefined {
    return this.items[this.focusedIndex];
  }

  move(delta: number): void {
    if (this.items.length === 0) return;
    const n = this.items.length;
    this.focusedIndex = ((this.focusedIndex + delta) % n + n) % n;
  }

  moveTo(index: number): void {
    if (this.items.length === 0) return;
    this.focusedIndex = Math.min(Math.max(index, 0), this.items.length - 1);
  }

  toggleFocused(): boolean {
    const item = this.focused();
    if (!item) return false;
    return this.toggle(item.id);
  }

  toggle(id: string): boolean {
    if (this.selected.has(id)) {
      this.selected.delete(id);
      return false;
    }
    if (this.items.some((s) => s.id === id)) this.selected.add(id);
    return this.selected.has(id);
  }

  selectAll(): void {
    for (const s of this.items) this.selected.add(s.id);
  }

  selectDefaults(): void {
    this.selected.clear();
    for (const s of this.items) {
      if (s.default_enabled !== false) this.selected.add(s.id);
    }
  }

  clear(): void {
    this.selected.clear();
  }

  selectedIds(): string[] {
    const wanted = this.selected;
    return this.items.filter((s) => wanted.has(s.id)).map((s) => s.id);
  }

  count(): number {
    return this.selected.size;
  }
}
