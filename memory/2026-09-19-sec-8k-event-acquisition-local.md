# SEC 8-K immutable acquisition (local fallback)

- summary: Completed immutable official SEC submissions acquisition for the fixed 527-symbol 2021-2023 coverage-limited sample. The first immutable attempt is retained as failed evidence because official current responses use ISO-8601 acceptance timestamps that the initial compact-only parser rejected. A regression test reproduced the failure, the parser was corrected without altering the failed artifact, and a new v2 external snapshot completed from 461 exact CIK responses plus all exact declared historical fragments. The canonical v2 snapshot has SHA-256 `2acd2c419dc8936a30c158f674e842de9d10c700f2295be610db478d14ff2ef1`, 12,487 categorized symbol-filings, 415 represented symbols, 414 unique issuers, 414 symbol/CIK groups with at least three filings, all three training years, and the same 65 preserved unmatched symbols. The preregistered 300-issuer and 5,000-event coverage gate passes. No development/consumed data or execution state was touched.
- stage: training-acquisition
- kpi_version: sec-8k-event-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:training-acquisition, strategy:sec-8k-event, status:coverage-passed
- next_step: Build the preregistered next-session, three-session causal feature cache from the canonical v2 snapshot, retain the failed v1 artifact, then run the frozen 400-cell grid only after feature and hash verification.

MCP memory was unavailable in this session, so this file is the required local fallback and should be copied into MCP when that service is restored.
