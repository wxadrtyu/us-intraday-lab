# Full-market tail-shape implementation plan

- summary: Froze a six-task TDD implementation plan for the 400-cell full-market daily tail-shape campaign, including family-and-lookback score binding, causal return-distribution features, fail-closed open-to-open portfolios, atomic checkpoints, immutable-source runner, and ordered terminal gates.
- stage: implementation-plan
- kpi_version: v7795-v8697 unchanged hard gates
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:implementation-plan, strategy:full-market-tail-shape-v1, status:preregistered
- next_step: Implement Task 1 contract tests and frozen 400-cell grid, then proceed sequentially under TDD.
- memory_backend: local fallback because codex-mcp-memory is unavailable in this runtime; must be backfilled when MCP becomes available.
- prohibited: news, announcements, regulatory data, SEC forms, issuer events, broker access, Paper activation, order routing, monitoring-pool changes.
