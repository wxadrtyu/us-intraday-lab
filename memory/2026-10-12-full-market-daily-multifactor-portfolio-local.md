---
type: strategy-hypothesis
summary: Implemented fail-closed equal-weight overlapping cohorts with immutable selections shared by 9 bp, 18 bp, and one-session delayed scenarios.
stage: portfolio-engine
kpi_version: full-market-daily-multifactor-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:portfolio-engine
  - strategy:full-market-daily-multifactor
  - status:implemented
next_step: Add atomic source/design/code/gate checkpoints and sequential 400-cell discovery evaluation against the frozen full-market inputs.
---

MCP memory was unavailable, so this is the required local fallback. Each
rebalance selects the deterministic top-K ranking once. The identical selection
digest is then reused for standard 9 bp, 18 bp cost stress, and one-session
delayed entry. Each cohort is equal-weighted across symbols and active cohorts
are equal-weighted through time. Entry, intermediate close-to-close, and exit
returns follow the global session calendar.

A missing bar anywhere on any selected holding path invalidates the scenario;
it is never cash, zero return, forward-filled, or removed after observing
performance. Tests verify cost arithmetic, delay timing, selection parity,
overlap, and fail-closed missingness. Ten focused tests pass and focused Ruff
checks are clean. No full return grid, broker, Paper, order route, or monitoring
pool was opened or changed.
