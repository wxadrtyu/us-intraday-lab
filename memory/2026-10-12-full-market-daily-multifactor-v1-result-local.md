# Full-market daily multifactor v1 result (local fallback)

- summary: Frozen 400-cell full-market long-horizon daily technical multifactor campaign completed with zero basic pre-null survivors. Of 400 cells, 396 failed closed because at least one selected holding path contained a missing bar or an explicit zero-liquidity source row; only four cells were valid, all in the liquidity-confirmed-breakout family, and none met the unchanged return, drawdown, information-ratio, z-score, and fold gates. The strongest valid standard 9bp case returned 13.11% annualized with 36.69% maximum drawdown, IR 0.704, z 1.217, and 2/5 positive folds; its 18bp and one-session-delay variants also failed. This family is frozen and must not be rescued or retuned.
- stage: consumed-period-pre-null-screen
- kpi_version: full-market-daily-multifactor-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:consumed-period-pre-null-screen, strategy:full-market-daily-multifactor-v1, status:rejected
- provenance: daily_source_sha256=0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701; universe_sha256=3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81; design_sha256=c128c9bbc9094f6acae90638e82aeb57225c82d43230a3cec01b723ff5dd80cf; code_sha256=66fe6032f2b9420c5fbd4e703019c99734c666446a897c6b13a94c8fd5279c52; gate_sha256=a9601cbd3ae1bd40d189d8b99e9a9055042a32f392fa39a8c290f3a41763eebf; final_chain_sha256=9e8fb79511f08c627b4294faedea15bd2d7f681cdb944249ced7294f580cce42
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN; missing data was never treated as cash or zero return.
- next_step: Freeze this entire five-family grid and preregister a genuinely different full-market technical return source using only allowed price, volume, volatility, breadth, or technical microstructure data. Do not run neighborhood, Bonferroni, or native maxT because no cell passed the basic pre-null gate.

