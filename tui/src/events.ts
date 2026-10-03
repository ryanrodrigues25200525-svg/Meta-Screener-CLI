import type {
  DashboardRunState,
  RunEvent,
  ScreenerFinishedEvent,
  ScreenerRunState,
  TopRow,
} from "./types.js";

const MAX_LOG_LINES = 200;

export function parseEventLine(raw: string, fallbackRunId = "unknown"): RunEvent | null {
  const line = raw.trim();
  if (line === "") return null;
  let data: Record<string, unknown>;
  try {
    data = JSON.parse(line) as Record<string, unknown>;
  } catch {
    return { type: "error", run_id: fallbackRunId, message: `Non-JSON output: ${line.slice(0, 200)}` };
  }
  if (typeof data.type !== "string" || typeof data.run_id !== "string") {
    return { type: "error", run_id: fallbackRunId, message: `Malformed event (missing type/run_id): ${line.slice(0, 200)}` };
  }
  return data as unknown as RunEvent;
}

export function blankRunState(): DashboardRunState {
  return { runId: null, running: false, overall: "idle", byScreener: {}, lastFinishedAt: null };
}

function ensureEntry(state: DashboardRunState, id: string): ScreenerRunState {
  let entry = state.byScreener[id];
  if (!entry) {
    entry = { status: "pending", log: [] };
    state.byScreener[id] = entry;
  }
  return entry;
}

function pushLog(entry: ScreenerRunState, line: string): void {
  entry.log.push(line);
  if (entry.log.length > MAX_LOG_LINES) {
    entry.log.splice(0, entry.log.length - MAX_LOG_LINES);
  }
}

function sanitizeTop(top: unknown): TopRow[] | undefined {
  if (!Array.isArray(top)) return undefined;
  const rows: TopRow[] = [];
  for (const row of top) {
    if (typeof row !== "object" || row === null) continue;
    const r = row as Record<string, unknown>;
    if (typeof r.rank !== "number" || typeof r.ticker !== "string") continue;
    rows.push({
      rank: r.rank,
      ticker: r.ticker,
      name: typeof r.name === "string" ? r.name : "",
      detail: typeof r.detail === "string" ? r.detail : "",
    });
  }
  rows.sort((a, b) => a.rank - b.rank);
  return rows;
}

export function applyEvent(state: DashboardRunState, event: RunEvent): DashboardRunState {
  switch (event.type) {
    case "run_started": {
      state.runId = event.run_id;
      state.running = true;
      state.overall = "running";
      return state;
    }
    case "screener_started": {
      const entry = ensureEntry(state, event.screener_id);
      entry.status = "running";
      return state;
    }
    case "output_line": {
      if (typeof event.screener_id !== "string" || event.screener_id.length === 0) return state;
      const entry = ensureEntry(state, event.screener_id);
      pushLog(entry, event.line);
      return state;
    }
    case "screener_finished": {
      const finished = event as ScreenerFinishedEvent;
      const entry = ensureEntry(state, finished.screener_id);
      entry.exitCode = finished.exit_code;
      entry.summary = typeof finished.summary === "string" ? finished.summary : entry.summary;
      entry.reportPath = typeof finished.report_path === "string" ? finished.report_path : entry.reportPath;
      const top = sanitizeTop(finished.top);
      if (top) entry.top = top;
      if ((finished.status ?? "") === "ok" && finished.exit_code === 0) {
        entry.status = "ok";
      } else if (/rate.?limit/i.test(finished.status ?? "")) {
        entry.status = "stopped";
      } else {
        entry.status = "failed";
      }
      return state;
    }
    case "run_finished": {
      state.running = false;
      state.overall = event.status;
      state.lastFinishedAt = Date.now();
      return state;
    }
    case "error": {
      state.overall = `error: ${event.message}`;
      return state;
    }
  }
}

/** Rankings come only from validated `top` rows; otherwise show summary/report. */
export function describeResult(entry: ScreenerRunState | undefined): string {
  if (!entry) return "Not run yet.";
  if (entry.status === "running") return "Running…";
  if (entry.status === "pending") return "Not run yet.";
  const parts: string[] = [];
  if (entry.top && entry.top.length > 0) {
    for (const row of entry.top.slice(0, 10)) {
      const label = row.name && row.name !== row.ticker ? `${row.ticker} — ${row.name}` : row.ticker;
      parts.push(`#${row.rank} ${label}${row.detail ? ` · ${row.detail}` : ""}`);
    }
    return parts.join("\n");
  }
  if (entry.summary) parts.push(entry.summary);
  else parts.push(entry.status === "ok" ? "Finished OK (no ranked tickers)." : `Finished: ${entry.status}.`);
  if (entry.reportPath) parts.push(`Report: ${entry.reportPath}`);
  return parts.join("\n");
}
