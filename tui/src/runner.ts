import { applyEvent, blankRunState, parseEventLine } from "./events.js";
import { buildRunnerCommand } from "./runtime.js";
import type { DashboardRunState, RunEvent } from "./types.js";

export type RunEventCallback = (event: RunEvent) => void;

export interface ActiveRun {
  runId: string;
  proc: Bun.Subprocess;
  promise: Promise<number>;
}

/**
 * Per-stream line splitter with private buffer/decoder state.
 * Create one instance per stream so partial chunks from stdout and
 * stderr can never interleave in a shared buffer.
 */
export function createLineAccumulator(onLine: (line: string) => void): {
  push: (chunk: Uint8Array) => void;
  flush: () => void;
} {
  let buffer = "";
  const decoder = new TextDecoder();
  return {
    push(chunk: Uint8Array): void {
      buffer += decoder.decode(chunk, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n")) >= 0) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        onLine(raw);
      }
    },
    flush(): void {
      const tail = (buffer + decoder.decode()).trim();
      buffer = "";
      if (tail !== "") onLine(tail);
    },
  };
}

/** Drain a byte stream line-by-line with its own buffer/decoder state. */
export async function consumeLines(
  stream: ReadableStream<Uint8Array> | null,
  onLine: (line: string) => void,
): Promise<void> {
  if (!stream) return;
  const reader = stream.getReader();
  const acc = createLineAccumulator(onLine);
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) acc.push(value);
    }
    acc.flush();
  } finally {
    reader.releaseLock();
  }
}

/**
 * Spawn the Python CLI with the Task 2 JSONL contract and stream events.
 * Throws if a run is already active (no overlapping runs).
 *
 * stdout carries JSONL run events; stderr carries plain-text diagnostics.
 * Each stream gets its own buffer/decoder state, and stderr lines are
 * never parsed as run events.
 */
export async function startRunner(opts: {
  python: string;
  root: string;
  ids: string[];
  active: ActiveRun | null;
  state: DashboardRunState;
  onEvent: RunEventCallback;
  onStderr?: (line: string) => void;
}): Promise<{ active: ActiveRun; state: DashboardRunState }> {
  if (opts.active) throw new Error("A run is already in progress.");
  if (opts.ids.length === 0) throw new Error("Select at least one workflow first.");
  const command = buildRunnerCommand(opts.python, opts.root, opts.ids);
  const proc = Bun.spawn(command, {
    stdout: "pipe",
    stderr: "pipe",
    env: { ...process.env },
  });

  let runId = `run-${Date.now()}`;
  const state = opts.state;
  const onEvent = opts.onEvent;
  const onStderr = opts.onStderr;

  const consumeStdout = consumeLines(proc.stdout as unknown as ReadableStream<Uint8Array>, (raw) => {
    const event = parseEventLine(raw, runId);
    if (!event) return;
    if (event.run_id) runId = event.run_id;
    applyEvent(state, event);
    onEvent(event);
  });

  const consumeStderr = consumeLines(proc.stderr as unknown as ReadableStream<Uint8Array>, (line) => {
    if (line.trim() === "") return;
    onStderr?.(line);
  });

  const promise = (async () => {
    await Promise.all([consumeStdout, consumeStderr]);
    const exitCode = await proc.exited;
    // If the CLI exited without a run_finished event (older runner), close the run honestly.
    if (state.running) {
      const fallback: RunEvent = {
        type: "run_finished",
        run_id: runId,
        status: exitCode === 0 ? "ok" : `failed (${exitCode})`,
      };
      applyEvent(state, fallback);
      onEvent(fallback);
    }
    return exitCode;
  })();

  return { active: { runId, proc, promise }, state };
}

export function initialRunState(): DashboardRunState {
  return blankRunState();
}
