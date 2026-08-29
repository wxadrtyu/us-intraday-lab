# v3169-v3268 leveraged/underlying residual campaign

## Decision

Reject the whole campaign. None of the 300 retained frontier records passed the
preregistered pre-factory-null gates, so no native-null run was warranted and no
candidate is eligible for research admission or Paper observation.

The result does not change the existing Paper pool or the separately recorded
user approval of v2968.

## Frozen design

- Versions: v3169-v3268 (100 hypotheses)
- New scan cells: 12,800
- Prior comparison cells: 124,905
- Cumulative comparison cells: 137,705
- Assets: TQQQ and SOXL, paired causally with QQQ and XLK
- Mechanisms: residual reversal/continuation, underlying-relative rotation,
  residual dispersion, flow absorption, volatility contraction and breakout
  confirmation
- Ranking periods: 2022-2023 training, 2024 and 2025
- Consumed diagnostics only: 2026Q1 and 2026 year to date
- Costs and timing: 9 bp standard, 18 bp stress and one additional five-minute
  entry delay
- Historical floor: 2018-2020 annualized return at least 15%, MDD below 20%
- Weak-market diagnostics: 2026Q1 and 2026 year-to-date total return at least 5%

## Batch result

- Status: `COMPLETE`
- Completed versions: 100/100
- Evaluated cells: 12,800
- Retained frontier records: 300
- Pre-factory-null hits: 0
- Runtime: 448.47 seconds
- Standard, 18 bp and delay primary-gate failures: 300/300 each
- Historical return/MDD gate failures: 300/300
- 2026Q1 diagnostic failures: 297/300
- 2026 year-to-date diagnostic failures: 230/300
- Four-of-five positive-fold failures: 243/300
- Parameter-neighborhood failures: 300/300
- Cumulative Bonferroni failures: 300/300

## Strongest development-period record

`lev-v3216-206b1725ff4a2274` used residual-flow absorption from decision bar 41
to exit bar 65 without a market-state filter.

| Scenario / period | Annualized return | MDD | IR |
| --- | ---: | ---: | ---: |
| 2024-2025, 9 bp | 26.97% | 7.55% | 0.96 |
| 2024-2025, 18 bp | 22.69% | 8.48% | 0.82 |
| 2024-2025, +5 minute delay | 23.09% | 8.21% | 0.94 |
| 2018-2020 historical | -21.49% | 44.26% | n/a |

Its consumed 2026Q1 return was -3.09% and consumed 2026 year-to-date return was
0.92%. Only two of five development folds were positive and its primary-gate
parameter-neighborhood share was zero. It therefore fails on return, IR,
history, folds, neighborhood and both 2026 diagnostics.

## Diagnostic examples

The best consumed-2026 return among each version's selected frontier included
v3180 at +23.51%, but that record produced only 15.72% annualized in 2024-2025,
8.53% under 18 bp, -23.26% annualized in 2018-2020, 46.19% historical MDD and
only +0.89% in consumed 2026Q1. This is a regime-specific diagnostic, not an
admissible strategy and not a basis for parameter ranking.

The orderly-rebound cash filter did not rescue the mechanism. For example,
v3235 had 13.20% development annualized return and +10.26% consumed 2026
year-to-date, but -18.09% historical annualized return, 39.84% historical MDD
and a slightly negative consumed 2026Q1 result.

## Falsification conclusion

Paired leveraged/underlying intraday residuals are not a sufficiently strong or
stable standalone payoff source in the tested universe and schedules. Their
apparent 2026 gains occur in records that fail the frozen development, history,
cost, delay or fold requirements. Further micro-tuning of this family is not
justified; the next campaign should change the economic return source.
