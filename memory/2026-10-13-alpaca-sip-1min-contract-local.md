# Alpaca SIP one-minute contract stage

- summary: Implemented the read-only historical SIP one-minute downloader and deterministic month/batch request identities under a distinct `alpaca_sip_1min_v1` namespace. Test-first verification observed missing-module failure, then three focused tests passed. The downloader requests 1Min, SIP, split adjustment, exact UTC bounds and asof; no trading client is constructed.
- stage: source-contract
- kpi_version: v7795-v8697 unchanged hard gates
- tags: project:quant-agent-team, market:cn_a, freq:intraday, stage:source-contract, strategy:full-market-5-10-minute, status:implemented
- next_step: Add exact regular-session normalization and fail-closed quality checks before any immutable shard publication.
- tests: 3 focused tests passed, Ruff passed, git diff check passed; one third-party websockets deprecation warning.
- outcome_reads: zero; cells_completed=0.
- memory_backend: local fallback because codex-mcp-memory is unavailable in this runtime; backfill when available.
