# SEC beneficial-ownership causal features (local fallback)

- summary: Built the preregistered causal SEC Schedule 13D/13G feature cache for the fixed 527-symbol 2021-2023 coverage-limited sample. A filing is available only on the first sample session strictly after SEC acceptance and remains active for exactly five sample sessions. The clustered-disclosure flag counts only causally available filings in the current/prior 20-session window and requires at least two. The cache has 388,745 event rows: 24,587 covered active-filing rows, 313,573 exact-identity rows without an active filing, and 50,585 preserved identity-unavailable rows. Raw inventory remains 9,550 qualifying symbol-filings, 9,530 unique issuer filings, 450 CIK issuers, 447 CIK issuers with at least three filings, and all three training years. Feature SHA-256 is `72f96b53a5b957fe30f9af11827980c986f1343384e6266c33b7e8c5814e71bc`. Eight focused snapshot/causality/atomic-output tests pass, Ruff is clean, and immutable resume produced identical bytes. No development/consumed data or execution state was touched.
- stage: feature-build
- kpi_version: sec-beneficial-ownership-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:feature-build, strategy:sec-beneficial-ownership, status:complete
- next_step: Implement and verify the preregistered source-completeness and coverage gate plus exact 400-cell cost/delay diagnostic, then run it only after the coverage gate passes.

MCP memory was unavailable in this session, so this file is the required local fallback and should be copied into MCP when that service is restored.
