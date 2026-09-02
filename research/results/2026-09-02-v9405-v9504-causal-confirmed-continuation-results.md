# v9405-v9504 causal confirmed-continuation results

## Outcome

- Status: `COMPLETE`
- Versions completed: 100/100
- New parameter cells: 12,800
- Cumulative comparison cells: 283,783
- Frontier records evaluated: 300
- Pre-factory-null passes: 0
- Native factory-null runs: 0
- Research-admissible candidates: 0
- Paper-pool changes: 0
- Elapsed time: 469.76 seconds

The preregistered single-window continuation family did not satisfy the
existing admission standard. No candidate was promoted or added to Paper.

## Best development result (rejected)

`lev-v9427-71b1b5d27fbe3459` used VWAP hold and sector broadening from decision
bar 17, with next-bar entry and exit at bar 29.

| Scenario | 2024-2025 annualized | MDD | IR |
|---|---:|---:|---:|
| 9 bp | 13.04% | 11.62% | 0.766 |
| 18 bp | 1.85% | 14.17% | -0.166 |
| Extra 5-minute delay, 9 bp | 9.67% | 13.13% | 0.531 |

The all-2026 consumed diagnostic was +15.51%, but 2026Q1 was only +1.54% and
neither period participated in selection. Historical 2018-2020 performance
failed in every scenario: standard annualized return was -18.49% with 38.20%
MDD. Parameter-neighborhood pass share was 0% and cumulative Bonferroni p was
1.0.

## Batch conclusion

Every frontier record failed the standard, 18 bp, historical, neighborhood,
and cumulative Bonferroni gates. All 300 also failed the delay primary gate.
The evidence does not support further local parameter tuning of a standalone
short-window continuation sleeve. Subsequent work should focus on causally
combining independently timed sleeves and exact forward parity.

The next unused research version is v9505.
