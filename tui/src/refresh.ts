export const DAILY_REFRESH_MS = 24 * 60 * 60 * 1000;

export interface RefreshSettings {
  enabled: boolean;
  lastRunAt: number | null;
}

/** Foreground-only daily refresh: disabled by default, no catch-up burst. */
export function shouldAutoRefresh(
  settings: RefreshSettings,
  now: number,
  running: boolean,
  selectedCount: number,
): boolean {
  if (!settings.enabled) return false;
  if (running) return false;
  if (selectedCount <= 0) return false;
  if (settings.lastRunAt === null) return false;
  return now - settings.lastRunAt >= DAILY_REFRESH_MS;
}

/** After any manual or automatic run starts, record it so only one refresh fires per day. */
export function markRunStarted(settings: RefreshSettings, now: number): void {
  settings.lastRunAt = now;
}
