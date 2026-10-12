---
memory_type: failed-experiment
summary: Daily-signal same-session technical multi-factor batch completed 400 valid cells but retained none; best cell had 8.57% annualized return, IR 0.57, and 21.35% drawdown.
stage: training-result
kpi_version: daily-signal-intraday-multifactor-training-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:training-result
  - strategy:daily-signal-intraday-multifactor-training-v1
  - status:rejected
next_step: Freeze the family and continue with a genuinely different technical-only hypothesis; do not load development data.
---

MCP memory was unavailable, so this is the required local fallback. Status was
COMPLETE with 400 cells, zero invalid cells, zero retained cells, and zero
retained families. Best valid cell: `diversified_quality`, pullback gap, lag 2,
top 5; annualized return 8.5712%, IR 0.5676, maximum drawdown 21.3544%.
Cell-table SHA-256:
`a153d70959bf43f1e63f9f49ae5c089b3bfa279fd4fdbb1230e8b574132480ec`.
No development/consumed period, event/news input, strategy version, Paper state,
monitoring state, broker route, or order path was opened.
