# SEC 8-K causal feature build (local fallback)

- summary: Built the preregistered causal SEC 8-K feature cache for the fixed 527-symbol 2021-2023 coverage-limited sample from the canonical immutable v2 submissions snapshot. Each filing becomes available only on the first sample session strictly after its acceptance date and remains active for exactly three sample sessions. The cache contains 388,745 event rows, including 42,871 covered event rows, 295,289 exact-mapped rows without an active filing, and 50,585 rows for the preserved identity-unavailable symbols. It retains all 12,487 categorized symbol-filings, 414 symbol/CIK groups with at least three filings, all three training years, and has SHA-256 `3cfa5cd22b0253ef62e2909d8f675ca774e75b128f7bef2ead761625180c6d42`. Twelve focused acquisition/data/causality tests pass and Ruff is clean. No development/consumed data or execution state was touched.
- stage: feature-build
- kpi_version: sec-8k-event-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:feature-build, strategy:sec-8k-event, status:complete
- next_step: Implement and verify the preregistered source-completeness and coverage gates plus the exact 400-cell five-category cost/delay diagnostic, then run it only against training.

MCP memory was unavailable in this session, so this file is the required local fallback and should be copied into MCP when that service is restored.
