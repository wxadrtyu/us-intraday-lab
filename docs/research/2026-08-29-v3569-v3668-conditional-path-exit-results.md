# v3569-v3668 conditional-path-exit campaign

## Decision

Reject the campaign and stop developing this multi-session reversal branch.
None of 300 frontier records passed the preregistered pre-factory-null gates.

## Result

- Versions: 100/100
- New cells: 12,800
- Cumulative comparison cells: 188,905
- Runtime: 453.87 seconds
- Pre-factory-null hits: 0
- Standard, 18 bp, delay, history, neighborhood and Bonferroni failures: 300/300 each
- 2026Q1 failures: 273/300
- Four-of-five positive-fold failures: 259/300

The strongest record was the fixed-hold baseline
`lev-v3589-7a46839f4d7e0aa2`, not a conditional exit:

| Scenario / period | Annualized return | MDD | IR |
| --- | ---: | ---: | ---: |
| 2024-2025, 9 bp | 31.95% | 17.33% | 0.93 |
| 2024-2025, 18 bp | 25.17% | n/a | 0.72 |
| 2024-2025, +5 minute delay | 32.76% | n/a | 0.96 |
| 2018-2020 historical | -5.08% | 30.14% | n/a |

Consumed 2026Q1 was -12.54% and consumed 2026 year-to-date was +34.77%. Its
five folds were +3.82%, -24.23%, -2.93%, -3.61% and +114.51%.

Fail-fast, nonpositive, asymmetric and two-stage retracement exits generally
destroyed the payoff because early adverse movement is part of the normal
reversal path. Profit locking did not exceed fixed holding. Further stop/target
tuning is not justified.
