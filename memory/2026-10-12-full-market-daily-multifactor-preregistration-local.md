---
type: strategy-hypothesis
summary: Preregistered a genuinely full-market long-horizon daily technical multifactor campaign with five immutable families and exactly 400 cells.
stage: preregistration
kpi_version: full-market-daily-multifactor-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:preregistration
  - status:frozen-design
next_step: Implement contract tests and the causal point-in-time panel loader before any return read.
---

MCP memory was unavailable, so this is the required local fallback. The design
uses only frozen SIP daily technical data and frozen monthly point-in-time
eligibility. It permanently excludes news, announcements, regulators, SEC
forms, issuer events, and fundamentals. The 2021-2026 period is explicitly
consumed; a survivor can only justify a new prospective shadow protocol.

The frozen families are residual momentum, trend quality, low-volatility trend,
liquidity-confirmed breakout, and trend-conditioned reversal. The fixed grid is
5 families x 4 rebalance intervals x 4 holdings x 5 top counts = 400 cells,
with 9/18 bp costs and a one-session delayed-entry stress. All inherited hard
gates and native maxT requirements remain fail-closed.
