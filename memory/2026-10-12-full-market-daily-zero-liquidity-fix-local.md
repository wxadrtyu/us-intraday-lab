---
type: failed-experiment
summary: The first full-market runner stopped before outcomes because 313228 source rows encode no-trade sessions as volume=trade_count=vwap=0; fixed the contract to preserve VWAP as missing and invalidate any selected zero-liquidity path.
stage: source-contract-debug
kpi_version: full-market-daily-multifactor-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-contract-debug
  - strategy:full-market-daily-multifactor
  - status:fixed-before-outcomes
next_step: Relaunch from the unchanged frozen source and verify that preparation reaches the atomic checkpoint before monitoring the 400 cells.
---

MCP memory was unavailable, so this is the required local fallback. Root-cause
SQL proved every invalid VWAP row had exactly zero volume and zero trades; none
was null, and no other OHLCV/trade-count field was invalid. These are explicit
no-trade source sentinels, not prices that may be imputed. The validator now
maps only this exact triple-zero sentinel to missing VWAP for technical-feature
calculation. It rejects every other nonpositive VWAP pattern.

Portfolio paths now retain volume and trade count and fail closed with
`SELECTED_PATH_ZERO_LIQUIDITY` if any selected holding path contains a no-trade
session. Nothing is treated as cash, zero return, forward-filled, or deleted
after ranking. Sixteen focused tests pass and focused Ruff checks are clean.
The failed run stopped before checkpoint creation and before any cell or return
metric completed; broker, Paper, routing, and monitoring state remained closed.
