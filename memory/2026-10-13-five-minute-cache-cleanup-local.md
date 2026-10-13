---
type: data-decision
summary: Four rebuildable DuckDB working databases totaling 12,179,783,680 bytes were moved to Recycle Bin; five-minute strategy returns remain gated pending a genuinely new technical field and exact execution-path coverage.
stage: five-minute-cache-cleanup-and-data-gate
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - status:data-gate-open-for-source-audit-only
next_step: Check accessible historical venue auction-imbalance technical data and point-in-time full-market coverage before any new five-minute return test; do not repeat exhausted bar or quote/trade families.
---

The four files were derived working databases, not raw SIP shards. Their
corresponding Parquet contexts and COMPLETE frozen reports remain. Research
cache now has 503 files and 536,955,863 bytes (0.50 GiB); moved files remain
recoverable in Recycle Bin and do not yet free physical disk space. Existing
five-minute source audit has 714,742,115 rows and 97.443652% aggregate
required-clock coverage, not an exact signal-entry-exit joint-coverage proof.
The bar-field information contract had 2,900 trials and zero admissions.
Exchange auction-imbalance technical data is not in local staging; official
historical exchange products exist but access and full-market stitching are
unverified. No returns, trading APIs, or monitoring state were touched.
MCP memory search/create were unavailable; backfill this local fallback later.
