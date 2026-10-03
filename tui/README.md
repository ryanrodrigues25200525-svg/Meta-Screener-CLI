# Meta Screener TUI

OpenTUI Core dashboard for the Meta Screener CLI. It renders `screeners.json`
workflows and consumes the Python runner's `--json-events` JSON Lines stream.
It never starts screen scripts directly.

## Install

```sh
bun install --cwd tui
```

Requires Bun 1.3+.

## Run

The Python launcher sets these and starts the dashboard with no arguments:

```sh
META_SCREENER_ROOT=/path/to/repo META_SCREENER_PYTHON=/path/to/python bun run --cwd tui start
```

Headless layout snapshots (no TTY needed):

```sh
bun run --cwd tui snapshot -- --width 110
bun run --cwd tui snapshot -- --width 60
```

## Keys

- `↑/↓` or `j/k`: move focus
- `space`: toggle select
- `a`: select all · `c`: clear
- `r` / `Enter`: run selected · `R`: run all default-enabled
- `d`: toggle details/output · `f`: toggle foreground daily refresh (off by default)
- `q` / `Esc` / `Ctrl+C`: quit with terminal cleanup

Runs are sequential; a second run cannot start while one is active. Rankings
come only from `top` rows; other workflows show summary/report paths.
A ticker shared with its company name renders once (`AAPL`, not `AAPL — AAPL`).

At startup (and in `--snapshot` mode) the dashboard restores the latest valid
record from `<root>/.meta-screener/runs/*.json` for display only — it never
launches screeners by itself. Malformed records and unknown screener IDs are
ignored. Startup preselects only the first default-enabled workflow
(`meta-overlap`); `R` still runs all defaults, and the opt-in daily refresh
reruns only the current selection (never with an empty selection).
