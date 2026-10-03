# One-off migrations — 2026

Historical source only. These ten scripts are dated, hard-coded Finance
Knowledge Graph repairs, backfills, and taxonomy fixes. They are **not**
registered in `screeners.json`, are not imported by any active workflow, and
are **not normal runnable screens** — do not run them as part of any screen
pass. They are preserved byte-for-byte so the vault's history stays auditable.

| File | Original purpose | Date |
| ---- | ---------------- | ---- |
| `kg_repair.py` | Deterministic vault integrity fixes: recovery-note moves, frontmatter repair, wikilink/bracket normalization, fundamentals structuring | Added to this repo 2026-10-02 |
| `kg_repair2.py` | Canonicalize theme company tokens to node titles, plus residual fixes | Added to this repo 2026-10-02 |
| `kg_repair3.py` | Collapse triple-bracket tokens, plus post-repair residual cleanup | Added to this repo 2026-10-02 |
| `kg_repair4.py` | Link-title fixes and missing Source nodes | Added to this repo 2026-10-02 |
| `kg_repair5.py` | Wire remaining evidence gaps from existing Claims nodes | Added to this repo 2026-10-02 |
| `backfill_comp.py` | Backfill competitor/partner/position fields onto PM-holding company nodes (idempotent) | Added to this repo 2026-10-02 |
| `backfill_comp2.py` | Same competitor/partner backfill for the remaining shortlist and watchlist nodes | Added to this repo 2026-10-02 |
| `backfill_verdicts_20260912.py` | PM decision 2026-09-12: write layer-3 verdicts and close holding gaps | 2026-09-12 (in filename) |
| `repair_verdict_fields_20260912.py` | Move verdict-date/review_date from note bodies into frontmatter (idempotent) | 2026-09-12 (in filename) |
| `driver_taxonomy_fix.py` | Rename the COPPER driver to BASE_METALS and write final coverage numbers | Added to this repo 2026-10-02 |

Reusable maintenance tools (`fix_wrapped_links.py`, `kg_validate.py`,
`graph_index.py`, `kg_links.py`) stay active at the repository root.
