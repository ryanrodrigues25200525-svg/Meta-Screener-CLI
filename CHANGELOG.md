# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Planned for 0.3.0: make the repository an understandable home for the existing
Python screeners and workflows, add a terminal dashboard, and let local AI
agents manage and run registered screens.

### Added

- `PYTHON_TOOLS.md` catalog of every tracked Python file, grouped by purpose,
  built from the modules' own docstrings.
- `archive/one-off-migrations/2026/` preserving the ten one-off vault
  repair/backfill scripts as historical source, with a readme describing
  their one-off nature.
- Planned: OpenTUI terminal dashboard launched by a bare `meta-screener`
  invocation, reading structured runner events instead of terminal formatting.
- Planned: optional local stdio MCP server (extra install) to list workflows
  and checks, preview run plans, run registered workflows, and create or
  remove named screens from existing checks.
- Planned: opt-in JSON Lines runner event mode and compact run summaries
  under an ignored `.meta-screener/` directory.

### Changed

- Planned: `VERSION` and package metadata advance to 0.3.0 at integration
  time; `pyproject.toml` alignment stays with the integration task.
- README links the new catalog and states the registry holds 17 workflows
  with 16 enabled by default (`screen-history` is optional).
