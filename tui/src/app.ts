import { BoxRenderable, TextRenderable, createCliRenderer } from "@opentui/core";
import { describeLeaderboard, describeResult } from "./events.js";
import { blankRunState, pushStderr } from "./events.js";
import { loadLatestSavedRun } from "./history.js";
import { groupByStage, orderedScreeners, SelectionModel } from "./registry.js";
import { markRunStarted, shouldAutoRefresh, toggleRefresh, type RefreshSettings } from "./refresh.js";
import { startRunner, type ActiveRun } from "./runner.js";
import { NARROW_WIDTH, resolveRuntime } from "./runtime.js";
import type { DashboardRunState, Registry } from "./types.js";

const DARK = {
  bg: "#0e1116",
  panel: "#161b22",
  border: "#2d333b",
  text: "#e6edf3",
  dim: "#8b949e",
  accent: "#58a6ff",
  ok: "#3fb950",
  err: "#f85149",
  warn: "#d29922",
};

export interface AppOptions {
  registry: Registry;
  root: string;
  python: string;
}

function statusDot(status: string | undefined): string {
  switch (status) {
    case "running":
      return "●";
    case "ok":
      return "✔";
    case "failed":
    case "stopped":
      return "✘";
    default:
      return "○";
  }
}

export function navText(selection: SelectionModel, run: DashboardRunState, groups: ReturnType<typeof groupByStage>): string {
  const lines: string[] = [];
  for (const group of groups) {
    lines.push(`${group.name}`);
    for (const s of group.screeners) {
      const idx = selection.items.findIndex((f) => f.id === s.id);
      const cursor = idx === selection.focusedIndex ? ">" : " ";
      const mark = selection.selected.has(s.id) ? "[x]" : "[ ]";
      const st = run.byScreener[s.id]?.status ?? "pending";
      lines.push(`${cursor} ${mark} ${statusDot(st)} ${s.id}`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

export function detailText(selection: SelectionModel, run: DashboardRunState, showDetails: boolean): string {
  const item = selection.focused();
  if (!item) return "No workflows registered.";
  const entry = run.byScreener[item.id];
  const lines: string[] = [];
  lines.push(`${item.name}`);
  lines.push(`${item.id} · ${item.provider}`);
  lines.push(item.description);
  lines.push("");
  lines.push("Result:");
  for (const l of describeResult(entry).split("\n").slice(0, 12)) lines.push(`  ${l}`);
  if (showDetails) {
    lines.push("");
    lines.push("Output:");
    const log = entry?.log ?? [];
    if (log.length === 0) lines.push("  (no output yet)");
    else for (const l of log.slice(-8)) lines.push(`  ${l.slice(0, 100)}`);
    const stderr = entry?.stderr ?? [];
    if (entry?.status === "failed" && stderr.length > 0) {
      lines.push("");
      lines.push("Diagnostics (stderr):");
      for (const l of stderr.slice(-8)) lines.push(`  ${l.slice(0, 100)}`);
    }
  }
  return lines.join("\n");
}

export function statusText(selection: SelectionModel, run: DashboardRunState, refresh: RefreshSettings): string {
  const total = selection.items.length;
  const sel = selection.selected.size;
  const running = Object.values(run.byScreener).filter((s) => s.status === "running").length;
  const ok = Object.values(run.byScreener).filter((s) => s.status === "ok").length;
  const bad = Object.values(run.byScreener).filter((s) => s.status === "failed" || s.status === "stopped").length;
  const runFlag = run.running ? `RUNNING (${running})` : run.overall;
  const refreshFlag = refresh.enabled ? "daily-refresh ON" : "daily-refresh OFF";
  return `workflows ${total} · selected ${sel} · ok ${ok} · errors ${bad} · ${runFlag} · ${refreshFlag}`;
}

export const FOOTER =
  "↑/↓·j/k move · space select · a all · c clear · r run · R run-all · d details · f refresh · q quit";

export async function runDashboard(opts: AppOptions): Promise<void> {
  const groups = groupByStage(opts.registry);
  const selection = SelectionModel.fromRegistry(opts.registry);
  // Restore the latest saved run record for display only; never launch here.
  let run: DashboardRunState = blankRunState();
  try {
    const saved = loadLatestSavedRun(opts.root, opts.registry);
    if (saved) run = saved.state;
  } catch {
    run = blankRunState();
  }
  const refresh: RefreshSettings = { enabled: false, lastRunAt: null };
  let showDetails = false;
  let active: ActiveRun | null = null;
  let destroyed = false;

  const renderer = await createCliRenderer({
    exitOnCtrlC: true,
    backgroundColor: DARK.bg,
  });

  const root = new BoxRenderable(renderer, {
    id: "root",
    flexDirection: "column",
    width: "100%",
    height: "100%",
    backgroundColor: DARK.bg,
    paddingLeft: 1,
    paddingRight: 1,
  });
  const header = new TextRenderable(renderer, {
    id: "header",
    content: "Meta Screener Dashboard",
    fg: DARK.text,
  });
  const status = new TextRenderable(renderer, {
    id: "status",
    content: "",
    fg: DARK.dim,
  });
  const body = new BoxRenderable(renderer, {
    id: "body",
    flexDirection: "row",
    flexGrow: 1,
    gap: 1,
  });
  const navBox = new BoxRenderable(renderer, {
    id: "nav",
    width: 34,
    border: true,
    borderColor: DARK.border,
    backgroundColor: DARK.panel,
    paddingLeft: 1,
    paddingRight: 1,
    flexShrink: 0,
  });
  const nav = new TextRenderable(renderer, { id: "nav-text", content: "", fg: DARK.text });
  navBox.add(nav);
  const detailBox = new BoxRenderable(renderer, {
    id: "detail",
    border: true,
    borderColor: DARK.border,
    backgroundColor: DARK.panel,
    paddingLeft: 1,
    paddingRight: 1,
    flexGrow: 1,
  });
  const detail = new TextRenderable(renderer, { id: "detail-text", content: "", fg: DARK.text });
  detailBox.add(detail);
  body.add(navBox);
  body.add(detailBox);
  const boardBox = new BoxRenderable(renderer, {
    id: "leaderboard",
    border: true,
    borderColor: DARK.border,
    backgroundColor: DARK.panel,
    paddingLeft: 1,
    paddingRight: 1,
    flexShrink: 0,
  });
  const board = new TextRenderable(renderer, { id: "leaderboard-text", content: "", fg: DARK.text });
  boardBox.add(board);
  const footer = new TextRenderable(renderer, { id: "footer", content: FOOTER, fg: DARK.dim });

  root.add(header);
  root.add(status);
  root.add(body);
  root.add(boardBox);
  root.add(footer);
  renderer.root.add(root);

  function paint(): void {
    if (destroyed) return;
    const width = renderer.width ?? 100;
    const narrow = width < NARROW_WIDTH;
    body.flexDirection = narrow ? "column" : "row";
    navBox.visible = true;
    header.content = narrow ? "Meta Screener" : "Meta Screener Dashboard — grouped workflows · JSONL runner";
    status.content = statusText(selection, run, refresh);
    if (narrow && !showDetails) {
      const item = selection.focused();
      const st = item ? (run.byScreener[item.id]?.status ?? "pending") : "pending";
      nav.content = item ? `> [${selection.selected.has(item.id) ? "x" : " "}] ${statusDot(st)} ${item.id}\n  ${item.name}` : "";
    } else {
      nav.content = navText(selection, run, groups);
    }
    detail.content = detailText(selection, run, showDetails);
    const boardLines = describeLeaderboard(run).split("\n").slice(0, 11);
    board.content = ["Leaderboard — most consistent across screeners", ...boardLines].join("\n");
    footer.content = narrow ? "↑↓ move · space sel · r run · d info · q quit" : FOOTER;
  }

  async function launch(ids: string[]): Promise<void> {
    if (active) {
      status.content = "A run is already in progress — wait for it to finish.";
      return;
    }
    if (ids.length === 0) {
      status.content = "Select at least one workflow first (space/a).";
      return;
    }
    markRunStarted(refresh, Date.now());
    try {
      // Stderr lines carry no screener id, so route each line to the
      // currently-running entry of this run; once nothing is running
      // (run finished), keep attributing to the last started screener.
      let stderrTarget: string | null = null;
      const started = await startRunner({
        python: opts.python,
        root: opts.root,
        ids,
        active,
        state: run,
        onEvent: (event) => {
          if (event.type === "screener_started") stderrTarget = event.screener_id;
          paint();
        },
        onStderr: (line) => {
          const running = ids.find((id) => run.byScreener[id]?.status === "running");
          const focused = selection.focused()?.id;
          const lastStarted = stderrTarget && ids.includes(stderrTarget) ? stderrTarget : null;
          const focusedInRun = focused && ids.includes(focused) ? focused : null;
          const target = running ?? lastStarted ?? focusedInRun ?? ids[0];
          if (target) pushStderr(run, target, line);
          paint();
        },
      });
      active = started.active;
      paint();
      void started.active.promise.then(() => {
        active = null;
        paint();
      });
    } catch (err) {
      status.content = err instanceof Error ? err.message : String(err);
    }
  }

  function shutdown(): void {
    if (destroyed) return;
    destroyed = true;
    try {
      active?.proc.kill();
    } catch {
      // best effort; terminal restore happens below regardless
    }
    renderer.destroy();
  }

  renderer.keyInput.on("keypress", (key) => {
    if (key.name === "q" || key.name === "escape") {
      shutdown();
      process.exit(0);
      return;
    }
    if (key.ctrl && key.name === "c") {
      shutdown();
      process.exit(0);
      return;
    }
    switch (key.name) {
      case "up":
      case "k":
        selection.move(-1);
        paint();
        return;
      case "down":
      case "j":
        selection.move(1);
        paint();
        return;
      case "space":
        selection.toggleFocused();
        paint();
        return;
      case "a":
        selection.selectAll();
        paint();
        return;
      case "c":
        selection.clear();
        paint();
        return;
      case "d":
        showDetails = !showDetails;
        paint();
        return;
      case "f":
        toggleRefresh(refresh, Date.now());
        paint();
        return;
      case "return":
      case "r":
        void launch(selection.selectedIds());
        return;
      case "R":
        void launch(orderedScreeners(opts.registry).filter((s) => s.default_enabled !== false).map((s) => s.id));
        return;
      default:
        return;
    }
  });

  renderer.on("resize", () => paint());

  // Opt-in foreground daily refresh of the current selection only:
  // checked on a foreground timer only. No background process, no catch-up
  // burst: at most one run per 24h window, never with an empty selection or
  // while a run is active.
  const timer = setInterval(() => {
    if (destroyed) return;
    if (shouldAutoRefresh(refresh, Date.now(), run.running, selection.count())) {
      void launch(selection.selectedIds());
    }
  }, 60_000);
  timer.unref?.();

  renderer.once("destroy", () => {
    destroyed = true;
    clearInterval(timer);
  });

  paint();
  await new Promise(() => {
    // Runs until quit; renderer owns the terminal session.
  });
}

export function resolveAppRuntime(tuiDir: string): { root: string; python: string } {
  return resolveRuntime(process.env as Record<string, string | undefined>, tuiDir);
}
