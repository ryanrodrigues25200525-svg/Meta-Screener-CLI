# MCP Server Guide

Local stdio MCP server for managing and running the workflows registered in `screeners.json`.

Source of truth: `screener_mcp.py`, `pyproject.toml`, `screeners.json`, `meta_screener_cli.py`.
The server delegates execution to the same `meta_screener_cli.py` runner used by the CLI/TUI.
Listing and planning never launch screeners.

## Setup (optional stdio server)

Requires Python 3.10+ (see `pyproject.toml`: `requires-python = ">=3.10"`).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-screening.txt
python -m pip install -e .
python -m pip install -e '.[mcp]'
```

The `mcp` extra installs `mcp>=2,<3` and provides the binary:

```toml
# pyproject.toml [project.scripts]
# meta-screener-mcp = "screener_mcp:main"
```

Verify the server is configured, then invoke `list_screeners` from OpenCode:

```bash
opencode mcp list
```

The server runs over local stdio transport (`build_server().run("stdio")` in `screener_mcp.py`).

## OpenCode configuration

Configure under `mcp.servers` with `type: "local"`. Use an absolute binary path.
See the [OpenCode local MCP server configuration](https://opencode.ai/v2/docs/mcp-servers)
reference for other process options.

```jsonc
// opencode.jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "meta-screener": {
        "type": "local",
        "command": ["/path/to/repo/.venv/bin/meta-screener-mcp"]
      }
    }
  }
}
```

Equivalent CLI command:

```bash
opencode mcp add meta-screener -- /path/to/repo/.venv/bin/meta-screener-mcp
opencode mcp list
```

## FINANCE_AI_HOME

`repository_root()` in `screener_mcp.py` resolves the managed repository as:

1. `$FINANCE_AI_HOME`, if set (expanded and resolved);
2. otherwise the directory containing `screener_mcp.py`.

Set `FINANCE_AI_HOME` when the `meta-screener-mcp` binary lives outside this repository checkout,
or when pointing at an isolated registry copy:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "meta-screener": {
        "type": "local",
        "command": ["/abs/path/to/.venv/bin/meta-screener-mcp"],
        "environment": {
          "FINANCE_AI_HOME": "/abs/path/to/Meta Screener CLI Public"
        }
      }
    }
  }
}
```

The registry path is always `<root>/screeners.json`; `register_screener` only accepts
repository-relative `.py` files that already exist under that root.

## Tools

Exactly seven tools are exposed by `build_server()` in `screener_mcp.py`. No other tools exist.

| Tool | Arguments | Intended use |
| --- | --- | --- |
| `list_screeners` | none | List registered workflows grouped by stage (`id`, `name`, `file`, `yahoo`, `default_enabled`, `provider`, `args`). Start here for valid screener IDs. |
| `list_checks` | none | List built-in `meta_screen.py` `@screen(name, category)` check names, categories, and criteria. Use before `create_screener`. |
| `plan_screeners` | `screener_ids: list[str]` | Preview ordered run plan for one or more screener IDs without launching anything. Returns `ordered_ids`, per-screener entries, and the CLI command vector. |
| `run_screeners` | `screener_ids: list[str]` | Run one or more registered screeners sequentially via `meta_screener_cli.py run --json-events --screener <id> ...`. Returns `returncode`, `rate_limited`, `ok`, `events`, `raw_output`. |
| `create_screener` | `screener_id: str`, `name: str`, `checks: list[str]`, `description: str \| None = None` | Create a named custom `meta_screen.py` profile in the `discovery` stage from existing check names. Sets `yahoo: true`, `default_enabled: false`, `args: ["--check", <check>, ...]`. |
| `register_screener` | `screener_id: str`, `name: str`, `file: str`, `stage: str`, `description: str \| None = None`, `provider: str \| None = None`, `yahoo: bool = False`, `default_enabled: bool = False`, `args: list[str] \| None = None`, `requirements: list[str] \| None = None`, `reads: list[str] \| None = None`, `writes: list[str] \| None = None` | Register an existing repository-contained `.py` workflow. `file` must be repository-relative, resolve inside the root, and end in `.py`. `stage` must already exist in `screeners.json`. |
| `remove_screener` | `screener_id: str` | Unregister a workflow without deleting its source file (`source_deleted` is always `false`). |

ID rules: new `screener_id` values must match `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$` and be unique.
MCP tools do not write arbitrary Python source.

## Examples

Screener IDs and stages below come from the shipped `screeners.json`
(for example `meta-overlap`, `sector-rotation`, `catalyst-calendar`;
stages `discovery`, `market-context`, `company-signals`, `events`, `tracking`).

List workflows and checks:

```text
list_screeners()
list_checks()
```

Preview before running (no execution):

```text
plan_screeners({"screener_ids": ["meta-overlap", "fundamental-rotation"]})
plan_screeners({"screener_ids": ["sector-rotation", "catalyst-calendar"]})
```

Run one or more workflows:

```text
run_screeners({"screener_ids": ["meta-overlap"]})
run_screeners({"screener_ids": ["sector-rotation", "market-sentiment"]})
```

Create a named profile from existing checks, then remove it:

```text
create_screener({
  "screener_id": "my-value-screen",
  "name": "My Value Screen",
  "checks": ["cheap fwd P/E (<15)", "low P/B (<2)"],
  "description": "Custom value subset."
})
remove_screener({"screener_id": "my-value-screen"})
```

Check names must match `list_checks()` exactly, for example
`"cheap fwd P/E (<15)"` or `"6m momentum leader (vs SPY)"`.
Custom profiles always land in the `discovery` stage.

Register an existing repository Python workflow, then remove the registration:

```text
register_screener({
  "screener_id": "my-context-scan",
  "name": "My Context Scan",
  "file": "market_sentiment.py",
  "stage": "market-context",
  "description": "Existing repo workflow registration.",
  "yahoo": true
})
remove_screener({"screener_id": "my-context-scan"})
```

`file` must already exist (for example `market_sentiment.py`, `sector_rotation.py`);
`stage` must be a known stage ID (`discovery`, `market-context`, `company-signals`, `events`, `tracking`).
Removing the registration keeps the `.py` file.

## Providers and registry (v0.4.0)

All 24 registry entries are Yahoo-only (`"yahoo": true`,
`"provider": "Yahoo Finance via yfinance"`). Company and event screens take an
explicit `--tickers` list or the shared built-in universe when run directly;
`run_screeners` launches them with their registry `args` only. The static
`macro-calendar` workflow is retired and no longer listed by `list_screeners`
(Yahoo supplies no macro calendar; the script is preserved at
`archive/econ_calendar.py`).

## Rate limiting

Yahoo-backed runs through `run_screeners` obey the same sequential CLI behavior as `meta_screener run`:

- Screeners run sequentially in registry stage order, not in parallel.
- The CLI defaults are one worker, 8 tickers per Yahoo batch, and a 15-second cooldown
  between workflows/stages and ticker batches (configurable 10-30s via the CLI).
- If Yahoo reports a rate limit (`too many requests`, `429`, `YFRateLimitError`),
  the run stops and does not retry automatically.
  `run_screeners` surfaces this as `rate_limited: true` with `ok: false`.
- Use `plan_screeners` (or `metascreener plan ...`) to review a selection before running it.
