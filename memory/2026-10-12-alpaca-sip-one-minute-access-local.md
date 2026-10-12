# Alpaca SIP one-minute access verified

- summary: After the user authorized continuation, a bounded read-only Alpaca historical-bars request proved the existing account can access SIP one-minute OHLCV/trade_count/VWAP with split adjustment and point-in-time asof. The AAPL 2023-01-03 probe returned 811 provider rows. This clears the credentials/access blocker but not the full-market capacity or coverage gate; no bulk data exists locally yet.
- stage: source-access-gate
- kpi_version: v7795-v8697 unchanged hard gates
- tags: project:quant-agent-team, market:cn_a, freq:intraday, stage:source-access-gate, strategy:full-market-5-10-minute, status:access-passed
- outcome_reads: zero; cells_completed=0.
- next_step: Preregister and implement a read-only immutable Alpaca SIP one-minute acquisition path, then run a bounded capacity probe before bulk acquisition over the frozen 15,399-symbol asset snapshot.
- safeguards: no credential values persisted; no trading APIs; no daily/overnight research; no exhausted five-minute family reuse; no broker, Paper, routing, or monitoring-pool change.
- memory_backend: local fallback because codex-mcp-memory is unavailable in this runtime; must be backfilled when MCP becomes available.
