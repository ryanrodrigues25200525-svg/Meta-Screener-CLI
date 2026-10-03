export const NARROW_WIDTH = 80;

export type LayoutMode = "normal" | "narrow";

export function layoutForWidth(width: number): LayoutMode {
  return width < NARROW_WIDTH ? "narrow" : "normal";
}

/** Resolve repo root + interpreter from the parent Python launcher env. */
export function resolveRuntime(env: Record<string, string | undefined>, tuiDir: string): {
  root: string;
  python: string;
} {
  const root = env.META_SCREENER_ROOT ?? parentDir(tuiDir);
  const python = env.META_SCREENER_PYTHON ?? "python3";
  return { root, python };
}

function parentDir(path: string): string {
  const trimmed = path.replace(/\/+$/, "");
  const idx = trimmed.lastIndexOf("/");
  if (idx <= 0) return "/";
  return trimmed.slice(0, idx);
}

export function joinPath(root: string, leaf: string): string {
  return root.replace(/\/+$/, "") + "/" + leaf.replace(/^\/+/, "");
}

/**
 * Runner command for the Task 2 JSONL contract. Accepts repeated --screener IDs.
 * Never builds a shell string; the caller spawns this argv directly.
 */
export function buildRunnerCommand(python: string, root: string, ids: string[]): string[] {
  const cli = joinPath(root, "meta_screener_cli.py");
  const command = [python, cli, "run", "--json-events"];
  for (const id of ids) command.push("--screener", id);
  return command;
}
