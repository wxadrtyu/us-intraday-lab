# Full-market session-decomposition portfolio engine (local fallback)

- summary: Implemented and fixture-tested family-specific exposure legs: close-to-next-open for overnight families and next-open-to-close for intraday families. Equal-weight overlapping cohorts share immutable selections across 9bp, 18bp, and one-session-delay scenarios. Selected missing or zero-liquidity exposure rows invalidate the entire cell. No production outcomes were read.
- stage: portfolio-engine
- kpi_version: full-market-session-decomposition-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:portfolio-engine, strategy:full-market-session-decomposition-v1, status:implemented
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN.
- next_step: Implement hash-bound atomic checkpoints and unchanged basic pre-null gates test-first.

