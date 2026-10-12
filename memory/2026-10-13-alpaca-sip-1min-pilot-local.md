# Alpaca SIP one-minute bounded capacity pilot

- summary: Existing read-only Alpaca credentials returned a one-session, 100-symbol SIP one-minute pilot: 10,994 provider rows, 10,162 regular-session rows, 70 returned symbols, 239,168 transient compressed bytes, 4.202 seconds. The sample is frozen by symbol-list SHA-256 1221aae690a87377656aa0c7a027be49272c8e4b98852815879823c4910429f6. The request and rows were not saved as immutable source shards; no coverage or strategy conclusion is claimed.
- stage: bounded-capacity-pilot
- kpi_version: v7795-v8697 unchanged hard gates
- tags: project:quant-agent-team, market:cn_a, freq:intraday, stage:bounded-capacity-pilot, strategy:full-market-5-10-minute, status:pilot-complete
- estimate: 2021-2023 has 753 XNYS sessions; extrapolation to 15,399 candidate symbols is about 1.178 billion rows and 25.8 GiB compressed, subject to sparse-symbol and provider effects.
- outcome_reads: zero; cells_completed=0.
- next_step: Freeze the one-minute acquisition design, implement an atomic and resumable source namespace with tests, save bounded immutable shards, and audit coverage before any strategy result.
- memory_backend: local fallback because codex-mcp-memory is unavailable in this runtime; backfill when available.
