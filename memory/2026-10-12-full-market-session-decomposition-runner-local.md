# Full-market session-decomposition runner (local fallback)

- summary: Implemented and tested the immutable-source session-decomposition runner. It verifies exact daily and point-in-time universe identities/counts, binds every family score to its frozen lookback, constructs all 20 family/lookback score columns from causal technical data, writes atomic 400-cell state externally, and publishes tracked aggregates only at completion. No full production outcome run has started yet.
- stage: runner
- kpi_version: full-market-session-decomposition-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:runner, strategy:full-market-session-decomposition-v1, status:implemented
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN.
- next_step: Launch the frozen 400-cell run sequentially, poll the atomic checkpoint, and freeze the result without changing any family, lookback, cost, delay, or gate.

