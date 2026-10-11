---
memory_type: data-decision
summary: Closed the news and regulatory-event research route, deleted 3,012,830,631 bytes of event-only data, and preregistered a strictly lagged daily technical multi-factor training family.
stage: design
kpi_version: daily-technical-multifactor-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:design
  - strategy:daily-technical-multifactor-v1
  - status:preregistered
next_step: Implement the frozen 400-cell training diagnostic with TDD, commit before outcome access, then run only 2021-2023 training data.
---

The event cleanup removed exact source caches and derived artifacts while preserving shared market data, code, Git history, and frozen rejection evidence. Recovery requires reacquisition.

The replacement daily SIP source is explicitly limited to 2020-07 through 2023-12: 672 parquet files plus 672 manifests, 243,705,913 bytes, SHA-256 `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`. The initial whole-directory hash was corrected before any outcome access because it included later files. Metadata-only coverage found 133,931 execution symbol-sessions with at least 60 strictly prior daily bars, spanning 526 symbols and all 753 training sessions. No development/consumed outcomes or execution state were accessed.
