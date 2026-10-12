---
type: failed-experiment
summary: A complete all-candidate 2023-12-29 SIP one-minute source grid passed hash/identity validation but failed point-in-time five-to-ten-minute execution-path coverage; no strategy returns were read.
stage: full-session-source-gate
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - source:alpaca_sip_1min_v1
  - status:rejected-source-coverage
next_step: Stop the 2021-2023 bulk download and outcome reads. Only a genuinely different, independently verified full-market intraday data path could reopen 5-10-minute technical strategy research; do not reuse exhausted 5-minute/quote-trade hypotheses.
---

All 154 frozen candidate shards for 2023-12-29 were acquired and deeply validated: 1,262,994 provider rows, 62,711 out-of-session exclusions, 1,200,283 regular-session bars, and 57 explicit provider-rejected symbols. Against the frozen point-in-time December universe, 2,167 symbols were eligible and 663,853 of 845,130 expected symbol-minutes were observed (78.55%). The illustrative fixed 09:55 ET twelve-consecutive-minute path was complete for only 859/2,167 (39.64%), far below the fixed 95% floor. The best start minute searched over the day reached only 1,798/2,167 (82.97%) and is descriptive, not an admissible selected clock. This is a complete single-session counterexample to a per-session full-market execution-path claim, not a measurement of all 2021-2023 sessions. Missing bars were never filled or treated as cash/zero return. Strategy outcomes, development/OOS ranking, and trading APIs remained closed.
