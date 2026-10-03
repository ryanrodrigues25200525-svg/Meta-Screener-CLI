import { readdirSync, readFileSync, statSync } from "node:fs";
import { applyEvent, blankRunState } from "./events.js";
import { joinPath } from "./runtime.js";
import type { DashboardRunState, Registry, ScreenerFinishedEvent } from "./types.js";

export interface SavedRunRecord {
  run_id: string;
  started_at?: string;
  finished_at?: string;
  status: string;
  exit_code: number;
  screeners: unknown[];
}

export interface LoadedHistory {
  record: SavedRunRecord;
  /** Display-only state: never running, empty per-screener logs. */
  state: DashboardRunState;
  finishedAtMs: number | null;
  sourcePath: string;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asRecord(value: unknown): SavedRunRecord | null {
  if (!isObject(value)) return null;
  if (typeof value.run_id !== "string" || value.run_id === "") return null;
  if (typeof value.status !== "string") return null;
  if (typeof value.exit_code !== "number") return null;
  if (!Array.isArray(value.screeners)) return null;
  const record: SavedRunRecord = {
    run_id: value.run_id,
    status: value.status,
    exit_code: value.exit_code,
    screeners: value.screeners,
  };
  if (typeof value.started_at === "string") record.started_at = value.started_at;
  if (typeof value.finished_at === "string") record.finished_at = value.finished_at;
  return record;
}

function parseFinishedAtMs(record: SavedRunRecord): number | null {
  if (!record.finished_at) return null;
  const ms = Date.parse(record.finished_at);
  return Number.isFinite(ms) ? ms : null;
}

/**
 * Latest valid saved run record under `<root>/.meta-screener/runs/*.json`.
 * Display-only: never launches screeners. Malformed records and unknown
 * screener IDs are ignored; every used field is validated first.
 */
export function loadLatestSavedRun(root: string, registry: Registry): LoadedHistory | null {
  const known = new Set(registry.screeners.map((s) => s.id));
  let files: string[];
  try {
    files = readdirSync(joinPath(root, ".meta-screener/runs")).filter((f) => f.endsWith(".json")).sort();
  } catch {
    return null;
  }
  let best: LoadedHistory | null = null;
  let bestKey = Number.NEGATIVE_INFINITY;
  for (const file of files) {
    const sourcePath = joinPath(root, `.meta-screener/runs/${file}`);
    let mtimeMs = 0;
    try {
      mtimeMs = statSync(sourcePath).mtimeMs;
    } catch {
      continue;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(sourcePath, "utf-8"));
    } catch {
      continue;
    }
    const record = asRecord(parsed);
    if (!record) continue;
    const finishedAtMs = parseFinishedAtMs(record);
    // Prefer logical time: finished_at wins whenever valid; mtime is only
    // a fallback for records missing/invalid finished_at so a touched copy
    // of a stale run cannot outrank a later logical run.
    const key = finishedAtMs ?? mtimeMs;
    if (best && key <= bestKey) continue;
    const state = toDisplayState(record, known, finishedAtMs);
    best = { record, state, finishedAtMs, sourcePath };
    bestKey = key;
  }
  return best;
}

function toDisplayState(
  record: SavedRunRecord,
  known: Set<string>,
  finishedAtMs: number | null,
): DashboardRunState {
  const state = blankRunState();
  state.runId = record.run_id;
  state.running = false;
  state.overall = record.status;
  state.lastFinishedAt = finishedAtMs;
  for (const row of record.screeners) {
    if (!isObject(row)) continue;
    if (typeof row.screener_id !== "string" || !known.has(row.screener_id)) continue;
    if (typeof row.status !== "string" || typeof row.exit_code !== "number") continue;
    const event: ScreenerFinishedEvent = {
      type: "screener_finished",
      run_id: record.run_id,
      screener_id: row.screener_id,
      status: row.status,
      exit_code: row.exit_code,
    };
    if (typeof row.summary === "string") event.summary = row.summary;
    if (typeof row.report_path === "string") event.report_path = row.report_path;
    if (Array.isArray(row.top)) event.top = row.top as ScreenerFinishedEvent["top"];
    if (typeof row.result_error === "string") event.result_error = row.result_error;
    applyEvent(state, event);
  }
  return state;
}
