---
type: data-decision
summary: SIP one-minute immutable shard writer and deep resume verifier completed with finite acquisition bounds; no strategy outcomes read.
stage: source-storage
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - source:alpaca_sip_1min_v1
  - status:validated
next_step: Add bounded CLI, run immutable representative pilot, then audit full-market one-minute coverage before any strategy evaluation.
---

The dedicated one-minute namespace now records a frozen acquisition contract, deterministic monthly symbol-batch request IDs, Zstd Parquet content hashes, provider rejection ledgers, source-row accounting, and request metadata. Resume verifies existing shards deeply and refuses partial publication, temporary artifacts, contract mismatch, identity mismatch, corruption, or ledger tampering. Acquisition requires an explicit finite shard stop. Seventeen focused tests and Ruff passed. This does not establish historical full-market coverage or a qualifying strategy.
