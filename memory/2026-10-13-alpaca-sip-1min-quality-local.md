---
type: data-decision
summary: SIP one-minute regular-session normalization and fail-closed row quality checks completed; no strategy outcomes read.
stage: source-quality
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - source:alpaca_sip_1min_v1
  - status:validated
next_step: Implement atomic shard publication and deep resume verification before a bounded immutable pilot.
---

The source normalizes to XNYS regular-session one-minute rows and records both original provider row count and out-of-session exclusions. Quality validation rejects duplicate symbol-minute keys, off-grid timestamps, malformed OHLC/volume/trade-count/VWAP, unexpected symbols, wrong source tags and out-of-bounds rows. Missing bars are not filled or interpreted as zero return. Twelve focused tests passed; Ruff passed. This is only a source-contract milestone, not full-market coverage or a strategy result.
