import { describe, expect, test } from "bun:test";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { blankRunState, pushStderr } from "../src/events.js";
import { detailText } from "../src/app.js";
import { SelectionModel } from "../src/registry.js";
import { consumeLines, createLineAccumulator, startRunner } from "../src/runner.js";
import type { RunEvent } from "../src/types.js";

describe("runner stream separation", () => {
  test("interleaved partial chunks keep stdout JSONL intact and stderr separate", async () => {
    const stdoutLines: string[] = [];
    const stderrLines: string[] = [];
    const out = createLineAccumulator((line) => stdoutLines.push(line));
    const err = createLineAccumulator((line) => stderrLines.push(line));
    const enc = new TextEncoder();
    const eventA = JSON.stringify({ type: "run_started", run_id: "r1" });
    const eventB = JSON.stringify({ type: "run_finished", run_id: "r1", status: "ok" });

    // Split stdout JSONL into partial chunks with stderr chunks interleaved
    // between them. A single shared buffer would mix the two streams and
    // corrupt the JSON; independent per-stream buffers must not.
    const stdoutParts = [
      eventA.slice(0, 10),
      eventA.slice(10) + "\n" + eventB.slice(0, 8),
      eventB.slice(8) + "\n",
    ];
    const stderrParts = ["warning par", "tial\nsecond stderr\n"];

    out.push(enc.encode(stdoutParts[0]));
    err.push(enc.encode(stderrParts[0]));
    out.push(enc.encode(stdoutParts[1]));
    err.push(enc.encode(stderrParts[1]));
    out.push(enc.encode(stdoutParts[2]));
    out.flush();
    err.flush();

    expect(stdoutLines).toEqual([eventA, eventB]);
    expect(stderrLines).toEqual(["warning partial", "second stderr"]);
    expect(() => {
      for (const line of stdoutLines) JSON.parse(line);
    }).not.toThrow();
  });

  test("consumeLines keeps concurrent stdout/stderr streams independent", async () => {
    function streamOf(chunks: string[], delayMs: number): ReadableStream<Uint8Array> {
      const enc = new TextEncoder();
      return new ReadableStream<Uint8Array>({
        async start(controller) {
          for (const chunk of chunks) {
            controller.enqueue(enc.encode(chunk));
            if (delayMs > 0) await new Promise((r) => setTimeout(r, delayMs));
          }
          controller.close();
        },
      });
    }
    const eventLine = JSON.stringify({ type: "run_started", run_id: "r2" });
    const stdoutSeen: string[] = [];
    const stderrSeen: string[] = [];
    await Promise.all([
      consumeLines(streamOf([eventLine.slice(0, 12), eventLine.slice(12) + "\n"], 5), (l) => stdoutSeen.push(l)),
      consumeLines(streamOf(["stderr partial ", "line\n"], 5), (l) => stderrSeen.push(l)),
    ]);
    expect(stdoutSeen).toEqual([eventLine]);
    expect(stderrSeen).toEqual(["stderr partial line"]);
  });

  test("startRunner reassembles split stdout JSON while stderr stays out of events", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tui-runner-"));
    writeFileSync(
      join(dir, "meta_screener_cli.py"),
      [
        `import sys, time`,
        `def out(s):`,
        `    sys.stdout.write(s); sys.stdout.flush()`,
        `def err(s):`,
        `    sys.stderr.write(s); sys.stderr.flush()`,
        `out('{"type": "run_started", "run_id": "r-interleave"}\\n')`,
        `out('{"type": "screener_started", "run_id": "r-interleave", "screener')`,
        `err('warning: partial download retry\\n')`,
        `time.sleep(0.05)`,
        `out('_id": "demo"}\\n')`,
        `out('{"type": "run_finished", "run_id": "r-interleave", "status": "ok"}\\n')`,
        ``,
      ].join("\n"),
    );
    const events: RunEvent[] = [];
    const stderrLines: string[] = [];
    const state = blankRunState();
    const started = await startRunner({
      python: "python3",
      root: dir,
      ids: ["demo"],
      active: null,
      state,
      onEvent: (e) => events.push(e),
      onStderr: (line) => stderrLines.push(line.trim()),
    });
    const exitCode = await started.active.promise;
    expect(exitCode).toBe(0);
    const types = events.map((e) => e.type);
    expect(types).toEqual(["run_started", "screener_started", "run_finished"]);
    expect(events[1]).toMatchObject({ screener_id: "demo" });
    expect(events.filter((e) => e.type === "error")).toEqual([]);
    expect(stderrLines).toContain("warning: partial download retry");
    expect(state.byScreener["demo"]?.status).toBe("running");
    expect(state.running).toBe(false);
  });
});

describe("failed-screener stderr diagnostics", () => {
  test("failing child stderr is captured and bounded", async () => {
    const dir = mkdtempSync(join(tmpdir(), "tui-runner-fail-"));
    writeFileSync(
      join(dir, "meta_screener_cli.py"),
      [
        `import sys`,
        `def out(s):`,
        `    sys.stdout.write(s); sys.stdout.flush()`,
        `def err(s):`,
        `    sys.stderr.write(s); sys.stderr.flush()`,
        `out('{"type": "run_started", "run_id": "r-fail"}\\n')`,
        `out('{"type": "screener_started", "run_id": "r-fail", "screener_id": "demo"}\\n')`,
        `err('Traceback (most recent call last):\\n')`,
        `err('Exception: boom\\n')`,
        `for i in range(300):`,
        `    err(f"boom detail line {i}\\n")`,
        `err('X' * 500 + '\\n')`,
        `out('{"type": "screener_finished", "run_id": "r-fail", "screener_id": "demo", "status": "failed", "exit_code": 1}\\n')`,
        `out('{"type": "run_finished", "run_id": "r-fail", "status": "failed (1)"}\\n')`,
        `sys.exit(1)`,
        ``,
      ].join("\n"),
    );
    const state = blankRunState();
    const seen: string[] = [];
    const started = await startRunner({
      python: "python3",
      root: dir,
      ids: ["demo"],
      active: null,
      state,
      onEvent: () => {},
      // Same wiring as the dashboard launch(): route stderr lines to the
      // currently-running screener entry with bounded storage.
      onStderr: (line) => {
        seen.push(line);
        const running = Object.keys(state.byScreener).find((id) => state.byScreener[id]?.status === "running") ?? "demo";
        pushStderr(state, running, line);
      },
    });
    const exitCode = await started.active.promise;
    expect(exitCode).toBe(1);
    // driven by stub child that exits 1 with stderr lines; assert seen contains diagnostic
    expect(seen.join("\n")).toMatch(/traceback|boom/i);
    // stderr never leaks into stdout JSONL event parsing
    expect(state.running).toBe(false);
    expect(state.byScreener["demo"]?.status).toBe("failed");
    // bounded storage: last 50 lines kept, each truncated to 200 chars
    const stored = state.byScreener["demo"]?.stderr ?? [];
    expect(stored.length).toBe(50);
    expect(stored.at(-1)).toHaveLength(200);
    expect(stored.join("\n")).toMatch(/boom/i);
  });

  test("detail view shows stderr diagnostics for failed runs only", () => {
    const selection = new SelectionModel([
      { id: "demo", name: "Demo", file: "demo.py", stage: "s", description: "d", provider: "test" },
    ]);
    const failed = blankRunState();
    failed.byScreener["demo"] = { status: "failed", exitCode: 1, log: ["out"], stderr: ["Traceback: boom"] };
    const failedText = detailText(selection, failed, true);
    expect(failedText).toMatch(/Diagnostics \(stderr\):/);
    expect(failedText).toMatch(/boom/);

    const ok = blankRunState();
    ok.byScreener["demo"] = { status: "ok", exitCode: 0, log: ["out"], stderr: ["some warning"] };
    expect(detailText(selection, ok, true)).not.toMatch(/Diagnostics \(stderr\):/);
  });
});
