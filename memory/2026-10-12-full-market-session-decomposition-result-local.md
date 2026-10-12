# Full-market session-decomposition v1 result (local fallback)

- summary: Frozen 400-cell full-market overnight/intraday session-decomposition campaign completed with zero basic pre-null survivors. Thirty-five cells were valid and 365 failed closed because selected exposure bars were missing or explicit zero-liquidity rows. Every valid cell failed the unchanged economic gates; even the highest valid standard-return cell lost 8.35% annualized with 28.40% drawdown, IR -1.244, z -2.151, and 1/5 positive folds, while its 18bp case lost 26.92% annualized. The entire family and its tested directions are frozen and must not be rescued, reversed after seeing outcomes, or retuned.
- stage: consumed-period-pre-null-screen
- kpi_version: full-market-session-decomposition-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, stage:consumed-period-pre-null-screen, strategy:full-market-session-decomposition-v1, status:rejected
- provenance: daily_source_sha256=0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701; universe_sha256=3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81; design_sha256=5d2b649a77c2c969b96f0e6d94072607b724e48044c3a3932ea97c751f70ceca; code_sha256=5ec17396c3686ed9aa118074356062f9b332157842a0760e7675305d9c97986f; gate_sha256=a9601cbd3ae1bd40d189d8b99e9a9055042a32f392fa39a8c290f3a41763eebf; final_chain_sha256=c1f08c81c0aab59fd888d9bcec4c9a2cb8de0f4844953832930465f8dfc14f04
- controls: consumed_period=true; independent_oos=false; paper_activation=false; order_route=FORBIDDEN; missingness was never cash, zero return, or post-outcome deletion.
- next_step: Skip neighborhood, Bonferroni, and native maxT because no cell passed the basic gate. Freeze this family and preregister a genuinely different full-market technical source rather than reversing the observed losing direction.

