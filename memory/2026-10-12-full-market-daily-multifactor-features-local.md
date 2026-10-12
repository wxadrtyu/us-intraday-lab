---
type: strategy-hypothesis
summary: Implemented and fixture-tested the five preregistered causal full-market daily technical feature families without loading strategy outcomes.
stage: feature-engineering
kpi_version: full-market-daily-multifactor-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:feature-engineering
  - strategy:full-market-daily-multifactor
  - status:implemented
next_step: Implement fail-closed equal-weight overlapping cohorts with immutable signal selections shared across 9 bp, 18 bp, and delayed scenarios.
---

MCP memory was unavailable, so this is the required local fallback. The five
implemented families are 252/21 market-beta and volatility-adjusted residual
momentum, 126-session regression trend quality, positive-trend low volatility,
liquidity- and VWAP-confirmed prior-high breakout, and five-session reversal
conditioned on a positive 126-session trend above its moving average.

The feature stage uses completed daily bars only, excludes the current close
from the prior-high window, applies deterministic session cross-sectional
winsorized ranks, and gates ineligible family observations to missing rather
than cash or zero. A future-mutation test proves earlier features are unchanged;
hand-calculated return and breakout checks also pass. Eight focused tests pass
and focused Ruff checks are clean. No return grid, broker, Paper, order route,
or monitoring-pool state was opened or changed.
