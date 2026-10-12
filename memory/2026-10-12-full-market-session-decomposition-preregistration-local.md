# Full-market session-decomposition preregistration (local fallback)

- summary: Preregistered a genuinely different full-market technical campaign based on overnight close-to-open versus regular-session open-to-close return decomposition. Breadth routing was not repeated and risk-budget repair was rejected. Five frozen causal families, four lookbacks, five refresh/life pairs, and four top counts create exactly 400 cells with unchanged 9/18bp, delay, fold, drawdown, IR, z, neighborhood, Bonferroni, and native maxT gates.
- stage: preregistration
- kpi_version: full-market-session-decomposition-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:preregistration, strategy:full-market-session-decomposition-v1, status:frozen-before-outcomes
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN; news/announcement/regulatory/SEC/issuer-event inputs forbidden.
- next_step: Write a TDD implementation plan, implement causal feature and exposure-leg fixtures, then run the frozen 400-cell consumed-period screen sequentially with atomic checkpoints.

