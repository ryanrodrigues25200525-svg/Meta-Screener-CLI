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
 * Spawn the Python CLI with the Task 2 JSONL contract and stream events.
 * Throws if a run is already active (no overlapping runs).
 */
export async function startRunner(opts: {
  python: string;
  root: string;
  ids: string[];
  active: ActiveRun | null;
  state: DashboardRunState;
  onEvent: RunEventCallback;
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
  let buffer = "";

  const consume = async (stream: ReadableStream<Uint8Array> | null) => {
    if (!stream) return;
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let idx: number;
        while ((idx = buffer.indexOf("\n")) >= 0) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 1);
          const event = parseEventLine(raw, runId);
          if (!event) continue;
          if (event.run_id) runId = event.run_id;
          applyEvent(state, event);
          onEvent(event);
        }
      }
      const tail = (buffer + decoder.decode()).trim();
      if (tail !== "") {
        const event = parseEventLine(tail, runId);
        if (event) {
          applyEvent(state, event);
          onEvent(event);
        }
      }
    } finally {
      reader.releaseLock();
    }
  };

  const promise = (async () => {
    await Promise.all([consume(proc.stdout as unknown as ReadableStream<Uint8Array>), consume(proc.stderr as unknown as ReadableStream<Uint8Array>)]);
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
