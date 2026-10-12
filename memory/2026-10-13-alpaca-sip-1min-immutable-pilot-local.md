---
type: data-decision
summary: Bounded read-only SIP one-minute pilot published one immutable 2023-12-29 shard; 8,652 regular-session rows from 45/100 frozen candidate symbols, with 55 explicit no-row symbols.
stage: immutable-pilot
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - source:alpaca_sip_1min_v1
  - status:functional-pilot-only
next_step: Implement point-in-time full-market one-minute coverage audit and capacity gate; do not read strategy outcomes before it passes.
---

The pilot used shard 0 of the frozen 15,399 candidate symbols and only 2023-12-29. The first 100 symbols are lexicographic and not a representative liquidity sample. Alpaca returned 9,364 rows, of which 712 were outside the regular session; 8,652 rows remained, covering 45 symbols. All 55 no-row symbols remain explicit. Parquet SHA-256 is 835ddaac507f34fc61579db45880848868a6dfc9167f80519ba16f1f4a9e3880, manifest SHA-256 is 160f0f9a828ccc8b4f98d9abf4878c459ca0f926811507cae7e053bbb9ca2537. Rerun verified the shard without redownload. No strategy outcomes or trading APIs were used.
