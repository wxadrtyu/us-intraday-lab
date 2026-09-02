# v9605-v9704 causal repriced v9292 successor

Status: `COMPLETE`, research rejection. No Paper allocation changed.

The batch rebuilt the economic idea behind v9292 without its retrospective
late gate. Every routed v42 parent now enters at
`max(native decision + 1, bar 24)`; the delay scenario enters one bar later.
The parent volatility target is recomputed from the repriced 9bp stream. The
fixed opening sleeve remains decision 2 / entry 3 / exit 11 and is never
exposed to the bar-23 veto.

## Outcome

- Versions: v9605-v9704 (100 frozen factor/threshold cells)
- Cumulative comparison cells: 284,483
- Runtime: 14.75 seconds
- Strict pre-native-null passes: 0
- Native-null runs: 0, because no candidate cleared every preceding gate

The highest development-ranked candidate was
`lev-v9672-2d13ee7ee4a75a5e`: 2024-2025 annualized return was 65.32% at 9bp,
50.78% at 18bp, and 60.82% with the extra five-minute delay. Corresponding
IRs were 2.09, 1.65, and 2.00; maximum drawdowns were 12.11%, 12.29%, and
12.83%. It failed the historical return and prospective global-evidence gates.

The most informative near-pass was `lev-v9642-b1cb2f09a0933b0e`. It passed all
economic, stress, fold, start-date, neighborhood, historical, and consumed-2026
gates. Its 2024-2025 annualized returns were 67.11%, 53.12%, and 65.37%, with
maximum drawdowns of 14.40%, 15.33%, and 14.13%. Historical 2018-2020 returns
were 27.74%, 16.77%, and 24.30%. Consumed diagnostics were +5.68% in 2026Q1
and +20.58% for all available 2026. It still failed the preregistered
prospective z-score gate: 2.199 versus the required 3.0.

## Rejection counts

- Prospective z-score below 3: 100/100
- Historical three-scenario gate failed: 99/100
- 2026Q1 diagnostic failed: 50/100
- Full-2026 diagnostic failed: 13/100
- 18bp primary gate failed: 11/100
- Delay primary gate failed: 10/100
- Neighborhood gate failed: 12/100
- Standard primary gate failed: 3/100

The causal repair retained enough return to justify a preregistered follow-up
focused on combining the historically robust growth-state signal with the
higher-IR volatility/liquidity signal. v9292 itself remains revoked and must
not be activated.
