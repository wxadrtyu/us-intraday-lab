---
memory_type: failed-experiment
summary: Daily technical risk-budget multi-factor batch completed all 400 training cells but retained none; 359 cells failed closed on missing next opens and the best valid cell returned only 5.14% annualized with IR 0.44.
stage: training-result
kpi_version: daily-risk-budget-multifactor-training-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:training-result
  - strategy:daily-risk-budget-multifactor-training-v1
  - status:rejected
next_step: Freeze the family and move to a genuinely different technical-only hypothesis; do not rescue cells or load development data.
---

MCP memory was unavailable, so this file is the required local fallback.
Frozen result: status COMPLETE, 400 cells, 359 invalid, zero retained cells,
zero retained families, and decision
`ABANDON_DAILY_RISK_BUDGET_NO_VERSION_CREATED`. The best valid cell was
`liquid_breakout`, lag 2, hold 2, top 10: 5.1362% annualized, IR 0.4414,
17.9093% maximum drawdown. Cell-table SHA-256 is
`bdc3e4d0d524d9573ae6fb594c20beda8f3828a437aaa5a39be1c185a9de3775`.
No development/consumed period, news/event data, strategy version, Paper state,
monitoring state, broker route, or order path was opened.
