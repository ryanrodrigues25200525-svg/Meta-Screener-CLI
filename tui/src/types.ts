export interface StageMeta {
  id: string;
  name: string;
  description: string;
}

export interface ScreenerMeta {
  id: string;
  name: string;
  file: string;
  stage: string;
  description: string;
  provider: string;
  yahoo?: boolean;
  default_enabled?: boolean;
  args?: string[];
}

export interface Registry {
  version: string;
  stages: StageMeta[];
  screeners: ScreenerMeta[];
}

export interface TopRow {
  rank: number;
  ticker: string;
  name: string;
  detail: string;
}

export type RunEventType =
  | "run_started"
  | "screener_started"
  | "output_line"
  | "screener_finished"
  | "run_finished"
  | "error";

export interface BaseEvent {
  type: RunEventType;
  run_id: string;
}

export interface RunStartedEvent extends BaseEvent {
  type: "run_started";
}

export interface ScreenerStartedEvent extends BaseEvent {
  type: "screener_started";
  screener_id: string;
}

export interface OutputLineEvent extends BaseEvent {
  type: "output_line";
  screener_id: string;
  line: string;
}

export interface ScreenerFinishedEvent extends BaseEvent {
  type: "screener_finished";
  screener_id: string;
  status: string;
  exit_code: number;
  summary?: string;
  report_path?: string;
  top?: TopRow[];
}

export interface RunFinishedEvent extends BaseEvent {
  type: "run_finished";
  status: string;
}

export interface ErrorEvent extends BaseEvent {
  type: "error";
  message: string;
}

export type RunEvent =
  | RunStartedEvent
  | ScreenerStartedEvent
  | OutputLineEvent
  | ScreenerFinishedEvent
  | RunFinishedEvent
  | ErrorEvent;

export type ScreenerStatus = "pending" | "running" | "ok" | "failed" | "stopped";

export interface ScreenerRunState {
  status: ScreenerStatus;
  exitCode?: number;
  summary?: string;
  reportPath?: string;
  top?: TopRow[];
  log: string[];
}

export interface DashboardRunState {
  runId: string | null;
  running: boolean;
  overall: string;
  byScreener: Record<string, ScreenerRunState>;
  lastFinishedAt: number | null;
}
