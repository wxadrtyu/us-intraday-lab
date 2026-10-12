# Full-market SIP one-minute source design and plan

- summary: Selected native Alpaca SIP one-minute bars for 5-10 minute intraday research after a bounded 100-symbol capacity pilot. Froze a market-data-only source namespace, 15,399-symbol candidate identity, 2021-2023 consumed window, month and deterministic 100-symbol batches, point-in-time asof, atomic shards, deep hash/resume checks, explicit missingness and provider rejection ledger, finite-range CLI, and pre-outcome coverage audit. The plan has five TDD stages.
- stage: source-design
- kpi_version: v7795-v8697 unchanged hard gates
- tags: project:quant-agent-team, market:cn_a, freq:intraday, stage:source-design, strategy:full-market-5-10-minute, status:preregistered
- next_step: Execute Task 1 with a failing test and implement only the frozen read-only one-minute downloader and partition contract.
- outcome_reads: zero; cells_completed=0.
- memory_backend: local fallback because codex-mcp-memory is unavailable in this runtime; backfill when available.
