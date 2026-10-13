---
type: data-decision
summary: Full-market SIP five-minute joint signal-entry-exit audit found only 1 of 20 fixed 5-10 minute routes above 95% aggregate coverage, and that route failed the floor in 37 of 96 months; no strategy returns were read.
stage: five-minute-joint-route-coverage
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - status:data-gate-not-robust
next_step: Audit genuinely new technical data with point-in-time full-market and exact 5-10 minute path coverage; never select the lone aggregate route after seeing its coverage or repeat the exhausted 2900-version bar contract.
---

Corrected audit used validated `monthly_universe_sip_v2` rather than an old
v1 exploratory denominator. Every route expected 4,520,552 symbol-sessions,
matching the frozen source audit. The best aggregate route had 4,297,713
complete paths (95.0705%) but 37/96 months below 95%; 19/20 routes missed
95% in aggregate. All 2021-2026 observations are consumed, not independent
OOS. Missing paths were failures, not cash or zero returns. No strategy returns
or trading APIs were touched. MCP memory search/create were unavailable, so
this is the local fallback for later backfill.
