import { describeResult } from "./events.js";
import type { GroupedStage } from "./registry.js";
import { layoutForWidth } from "./runtime.js";
import type { DashboardRunState, ScreenerMeta } from "./types.js";

export interface DashboardModel {
  groups: GroupedStage[];
  flat: ScreenerMeta[];
  focusedIndex: number;
  selected: Set<string>;
  run: DashboardRunState;
  showDetails: boolean;
  refreshEnabled: boolean;
  overall: string;
}

export interface RenderOptions {
  width: number;
  height: number;
}

function statusBadge(status: string): string {
  switch (status) {
    case "running":
      return "[RUN]";
    case "ok":
      return "[ OK]";
    case "failed":
      return "[ERR]";
    case "stopped":
      return "[STOP]";
    default:
      return "[ --]";
  }
}

function truncate(text: string, width: number): string {
  if (width <= 0) return "";
  if (text.length <= width) return text;
  if (width <= 3) return text.slice(0, width);
  return text.slice(0, width - 3) + "...";
}

export function renderDashboardText(model: DashboardModel, opts: RenderOptions): string {
  const mode = layoutForWidth(opts.width);
  const lines: string[] = [];
  const w = Math.max(opts.width, 20);

  lines.push(truncate("Meta Screener Dashboard  ·  dark  ·  " + model.overall, w));
  lines.push("-".repeat(Math.min(w, 120)));

  const selectedCount = model.selected.size;
  const runningCount = Object.values(model.run.byScreener).filter((s) => s.status === "running").length;
  const okCount = Object.values(model.run.byScreener).filter((s) => s.status === "ok").length;
  const errCount = Object.values(model.run.byScreener).filter(
    (s) => s.status === "failed" || s.status === "stopped",
  ).length;
  lines.push(`selected ${selectedCount} · running ${runningCount} · ok ${okCount} · errors ${errCount}`);

  if (mode === "narrow") {
    const item = model.flat[model.focusedIndex];
    lines.push(`-- focus ${model.focusedIndex + 1}/${model.flat.length} --`);
    if (item) {
      const mark = model.selected.has(item.id) ? "[x]" : "[ ]";
      const state = model.run.byScreener[item.id];
      lines.push(`${mark} ${item.id} ${statusBadge(state?.status ?? "pending")}`);
      lines.push(truncate(item.name, w));
      if (model.showDetails) {
        lines.push(truncate(item.description, w));
        for (const resultLine of describeResult(state).split("\n").slice(0, 8)) {
          lines.push(truncate("  " + resultLine, w));
        }
      } else {
        const first = describeResult(state).split("\n")[0] ?? "";
        lines.push(truncate("  " + first, w));
      }
    }
    lines.push(footerLine(w, true));
    return lines.join("\n");
  }

  // Normal: grouped nav + focused results side by side (text snapshot form).
  for (const group of model.groups) {
    lines.push(`## ${group.name} (${group.id})`);
    for (const s of group.screeners) {
      const idx = model.flat.findIndex((f) => f.id === s.id);
      const cursor = idx === model.focusedIndex ? ">" : " ";
      const mark = model.selected.has(s.id) ? "[x]" : "[ ]";
      const state = model.run.byScreener[s.id];
      lines.push(`${cursor}${mark} ${s.id} ${statusBadge(state?.status ?? "pending")} ${truncate(s.name, 40)}`);
    }
  }
  lines.push("");
  const focused = model.flat[model.focusedIndex];
  if (focused) {
    lines.push(`== ${focused.id} · ${focused.name} ==`);
    lines.push(truncate(focused.description, w));
    lines.push(`provider: ${focused.provider}`);
    for (const resultLine of describeResult(model.run.byScreener[focused.id]).split("\n").slice(0, 12)) {
      lines.push(truncate(resultLine, w));
    }
    const log = model.run.byScreener[focused.id]?.log ?? [];
    if (log.length > 0) {
      lines.push("-- output --");
      for (const logLine of log.slice(-5)) lines.push(truncate(logLine, w));
    }
    const failedEntry = model.run.byScreener[focused.id];
    const stderr = failedEntry?.stderr ?? [];
    if (failedEntry?.status === "failed" && stderr.length > 0) {
      lines.push("-- diagnostics (stderr) --");
      for (const errLine of stderr.slice(-8)) lines.push(truncate(errLine, w));
    }
  }
  lines.push(footerLine(w, false));
  return lines.join("\n");
}

function footerLine(width: number, narrow: boolean): string {
  const full = "↑/↓ move · space select · a all · c clear · r run · R run-all · d details · f refresh · q quit";
  const short = "↑↓ move · space sel · r run · q quit";
  return truncate(narrow ? short : full, width);
}

export const FOOTER_FULL = "↑/↓ move · space select · a all · c clear · r run · R run-all · d details · f refresh · q quit";
