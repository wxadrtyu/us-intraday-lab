# Full-market session-decomposition contract (local fallback)

- summary: Implemented and test-froze the 400-cell session-decomposition contract: five overnight/intraday families, four lookbacks, five refresh/life pairs, and four top counts. No outcome data was read by this stage.
- stage: contract
- kpi_version: full-market-session-decomposition-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:contract, strategy:full-market-session-decomposition-v1, status:implemented
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN.
- next_step: Implement causal overnight/intraday features test-first using only frozen technical inputs.

