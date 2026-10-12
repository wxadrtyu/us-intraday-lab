# Full-market one-minute data gap

- summary: Audited both frozen data roots for a one-minute or finer full-market source required by the new 5-10 minute holding constraint. Only 18 Alpaca IEX one-minute snapshots exist, each covering 16 or 21 symbols (36-symbol union), all marked quality_complete=false; no SIP one-minute source exists. The full-market SIP five-minute family is already consumed and prohibited from relabeling. Research therefore stopped before outcome loading with decision BLOCKED_FULL_MARKET_1MIN_SOURCE_MISSING.
- stage: source-coverage-gate
- kpi_version: v7795-v8697 unchanged hard gates
- tags: project:quant-agent-team, market:cn_a, freq:intraday, stage:source-coverage-gate, strategy:full-market-5-10-minute, status:blocked
- evidence: 18 manifests, 18,473,449 rows, 36 unique symbols, inventory SHA-256 e3857929b7538b43886a7bbe6eda5aac6e6f0367d3a832645ee636b151ce4cfc, all feed=iex, all quality_complete=false, no SIP 1-minute dataset.
- outcome_reads: zero; cells_completed=0.
- next_step: Obtain explicit authority and credentials for an immutable point-in-time full-market SIP one-minute or finer acquisition; otherwise no honest full-market 5-10 minute backtest is possible.
- prohibited_fallbacks: daily research, overnight holding, five-minute exhausted-family relabeling, fixed ETF universe, 16/21-symbol IEX scope, missing-as-cash or zero, Paper activation, broker/order routing, monitoring-pool changes.
- memory_backend: local fallback because codex-mcp-memory is unavailable in this runtime; must be backfilled when MCP becomes available.
