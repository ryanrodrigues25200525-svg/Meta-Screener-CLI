import { describe, expect, test } from "bun:test";
import { applyEvent, blankRunState, describeResult, parseEventLine } from "../src/events.js";

describe("JSON event handling", () => {
  test("blank lines are skipped", () => {
    expect(parseEventLine("   ")).toBeNull();
  });

  test("valid screener events parse and apply in order", () => {
    const state = blankRunState();
    const lines = [
      JSON.stringify({ type: "run_started", run_id: "r1" }),
      JSON.stringify({ type: "screener_started", run_id: "r1", screener_id: "meta-overlap" }),
      JSON.stringify({ type: "output_line", run_id: "r1", screener_id: "meta-overlap", line: "hello" }),
      JSON.stringify({
        type: "screener_finished",
        run_id: "r1",
        screener_id: "meta-overlap",
        status: "ok",
        exit_code: 0,
        summary: "done",
        report_path: "/tmp/report.md",
        top: [{ rank: 2, ticker: "B", name: "Bee", detail: "d2" }, { rank: 1, ticker: "A", name: "Ay", detail: "d1" }],
      }),
      JSON.stringify({ type: "run_finished", run_id: "r1", status: "ok" }),
    ];
    for (const line of lines) {
      const event = parseEventLine(line)!;
      applyEvent(state, event);
    }
    expect(state.running).toBe(false);
    expect(state.overall).toBe("ok");
    const entry = state.byScreener["meta-overlap"]!;
    expect(entry.status).toBe("ok");
    expect(entry.top!.map((r) => r.ticker)).toEqual(["A", "B"]);
    expect(entry.log).toEqual(["hello"]);
  });

  test("rankings render only from top rows", () => {
    const state = blankRunState();
    applyEvent(state, {
      type: "screener_finished",
      run_id: "r1",
      screener_id: "macro-calendar",
      status: "ok",
      exit_code: 0,
      summary: "5 upcoming events",
      report_path: "/tmp/econ.md",
    } as never);
    const text = describeResult(state.byScreener["macro-calendar"]);
    expect(text).toContain("5 upcoming events");
    expect(text).toContain("/tmp/econ.md");
    expect(text).not.toMatch(/#1 /);
  });

  test("failed and rate-limited finishes map honestly", () => {
    const state = blankRunState();
    applyEvent(state, {
      type: "screener_finished", run_id: "r1", screener_id: "a", status: "failed", exit_code: 1,
    } as never);
    applyEvent(state, {
      type: "screener_finished", run_id: "r1", screener_id: "b", status: "stopped (Yahoo rate limit detected)", exit_code: 2,
    } as never);
    expect(state.byScreener["a"]!.status).toBe("failed");
    expect(state.byScreener["b"]!.status).toBe("stopped");
  });

  test("malformed lines become error events, not crashes", () => {
    const bad = parseEventLine("not json at all", "r9")!;
    expect(bad.type).toBe("error");
    const missing = parseEventLine(JSON.stringify({ type: "output_line" }), "r9")!;
    expect(missing.type).toBe("error");
    const state = blankRunState();
    applyEvent(state, bad);
    expect(state.overall).toContain("error");
  });

  test("output log is bounded", () => {
    const state = blankRunState();
    applyEvent(state, { type: "screener_started", run_id: "r1", screener_id: "x" } as never);
    for (let i = 0; i < 250; i++) {
      applyEvent(state, { type: "output_line", run_id: "r1", screener_id: "x", line: `l${i}` } as never);
    }
    expect(state.byScreener["x"]!.log.length).toBe(200);
    expect(state.byScreener["x"]!.log.at(-1)).toBe("l249");
  });

  test("run-level output does not create a fake screener entry", () => {
    const state = blankRunState();
    const event = parseEventLine(JSON.stringify({
      type: "output_line",
      run_id: "r1",
      screener_id: null,
      line: "Stage cooldown: waiting 15s.",
    }));

    expect(event?.type).toBe("output_line");
    if (event) applyEvent(state, event);
    expect(state.byScreener).toEqual({});
  });
});
