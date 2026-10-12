# Full-market tail-shape preregistration (local fallback)

- summary: Preregistered a genuinely different full-market daily technical campaign based on return-distribution tail shape rather than trend direction, session decomposition, breadth routing, or exhausted quote/trade microstructure. Five fixed tail-shape families, four lookbacks, five rebalance/holding pairs, and four top counts create exactly 400 cells under unchanged costs, delay, missingness, economic, robustness, Bonferroni, and native maxT gates.
- stage: preregistration
- kpi_version: full-market-tail-shape-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:preregistration, strategy:full-market-tail-shape-v1, status:frozen-before-outcomes
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN; issuer-event and exhausted quote/trade inputs forbidden.
- next_step: Write the TDD implementation plan, then implement the frozen tail-shape contract, features, portfolio engine, checkpoints, and runner before reading outcomes.

