# SEC 8-K data-contract implementation (local fallback)

- summary: Implemented and verified the strict official SEC submissions contract for the fixed 527-symbol 2021-2023 coverage-limited sample. The contract validates required parallel arrays, selects only declared historical fragments intersecting training, parses exact comma-delimited items, preserves amendments and unmatched CIKs as rejection evidence, rejects conflicting duplicate accessions, and duplicates filings across share classes only through explicit exact-CIK identity rows. Six focused tests pass and Ruff is clean. No external acquisition, return evaluation, development data, execution path, Paper state, or pool state was touched.
- stage: data-contract
- kpi_version: sec-8k-event-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:data-contract, strategy:sec-8k-event, status:implemented
- next_step: Implement immutable acquisition around the frozen current submissions and exact declared historical fragments, verify resume and collision behavior with tests, then apply the preregistered coverage gate before any return grid.

MCP memory was unavailable in this session, so this file is the required local fallback and should be copied into MCP when that service is restored.
