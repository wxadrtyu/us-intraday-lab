# SEC beneficial-ownership snapshot (local fallback)

- summary: Built the immutable SEC Schedule 13D/13G training snapshot for the fixed 527-symbol 2021-2023 coverage-limited sample from the already frozen canonical SEC current submissions and exact declared historical fragments. Every listed source hash verified. Exact CIK mapping preserves 462 matched symbols and all 65 unmatched symbols. The snapshot contains 9,550 qualifying symbol-filing events across 451 symbols, 9,530 unique issuer filings, 450 unique CIK issuers, and 447 CIK issuers with at least three qualifying filings, with events present in 2021, 2022, and 2023. Snapshot SHA-256 is `22f1edcb3a1138c8b2df1367585215d0face081865ff1d575edf5e5164200641`; preserved-rejections SHA-256 is `5b1b8ff8b1a612ef8c065e8f24f531b3f5b9b4a8a2bad2db75f7a5e7ae786f0f`. The preregistered 300-issuer, 7,000-event, three-year source-coverage thresholds pass. No development/consumed data or execution state was touched.
- stage: source-snapshot
- kpi_version: sec-beneficial-ownership-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:source-snapshot, strategy:sec-beneficial-ownership, status:complete
- next_step: Build and verify the preregistered next-session, five-session causal features and prior-20-session clustered-disclosure indicator, then apply the complete coverage gate before any return evaluation.

MCP memory was unavailable in this session, so this file is the required local fallback and should be copied into MCP when that service is restored.
