# Stop daily and long-horizon research

- summary: User explicitly prohibited further daily-frequency research and required high-frequency strategies whose single-trade holding period is no more than 5-10 minutes. The preregistered full-market daily tail-shape campaign is frozen before implementation and before any outcome read; its uncommitted contract code and tests were removed. Existing daily designs/results remain only as immutable rejection or abandoned-design evidence.
- stage: research-scope-decision
- kpi_version: v7795-v8697 unchanged hard gates
- tags: project:quant-agent-team, market:cn_a, freq:intraday, stage:research-scope-decision, strategy:full-market-tail-shape-v1, status:frozen
- next_step: Audit the frozen intraday data inventory and exhausted-family registry, then preregister a genuinely distinct full-market 1-minute-input strategy with a 5-minute preferred and 10-minute maximum holding period.
- constraints: no daily or overnight strategy research; no news, announcements, regulatory data, SEC forms, issuer events, fixed small-ETF universe, broker access, Paper activation, order routing, or monitoring-pool changes.
- outcome_reads: zero; tail-shape campaign never opened return outcomes.
- memory_backend: local fallback because codex-mcp-memory is unavailable in this runtime; must be backfilled when MCP becomes available.
