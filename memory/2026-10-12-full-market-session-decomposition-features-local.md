# Full-market session-decomposition features (local fallback)

- summary: Implemented and fixture-tested causal overnight close-to-open and regular-session open-to-close features plus the five frozen cross-sectional family scores. Validation rejects forbidden issuer/event fields and invalid bars; exact triple-zero liquidity rows preserve VWAP as explicit missing input. No strategy outcomes were read.
- stage: features
- kpi_version: full-market-session-decomposition-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:features, strategy:full-market-session-decomposition-v1, status:implemented
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN.
- next_step: Implement overnight-only and intraday-only exposure portfolios with exact missingness, cost, delay, and cohort behavior test-first.

