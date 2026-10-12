---
type: data-decision
summary: Six bounded immutable one-minute SIP shards show severe execution-path missingness in a point-in-time 2023-12-29 pilot; full-market coverage remains unproven and strategy outcomes remain closed.
stage: point-in-time-path-diagnostic
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - source:alpaca_sip_1min_v1
  - status:coverage-unproven
next_step: Do not run strategy metrics; decide source feasibility from a predeclared full-market one-minute coverage gate, preserving all missing bars and consumed-period status.
---

Six deterministic 100-symbol shards spanning candidate indices 0/25/50/75/100/125 on 2023-12-29 yielded 80 point-in-time eligible symbols. Only 24,757 of 31,200 eligible symbol-minutes were observed (79.35%). An illustrative 12-consecutive-minute 09:55 ET path was complete for 28/80 (35%); even the descriptive best start minute across the day reached only 68/80 (85%). These are sample diagnostics, not a full-market pass/fail or a tradable strategy. No outcomes were read, no missing bar was filled, and no trading API was touched. Audit code and tests were added; all strategy metrics remain prohibited until a complete source grid and fixed coverage gate pass.
