# v957-v1158 cash routing and dynamic substitution results

## Outcome

The v957-v1056 full-portfolio cash-routing hypothesis was falsified. The subsequent v1057-v1156
dynamic sleeve-substitution campaign produced `lev-v1102-b4e2a7c1b73a5b95`, which passed its
routed-component null and all joint-neighborhood cells. v1102 is a usable inherited-exception
candidate and a stronger alternative to v925. It was not added to the Alpaca Paper pool.

## Rejected v957-v1056 direction

The campaign tested 100 versions and 400 cells in 6.49 seconds. Four causal prior-close
multi-factor states gated the entire portfolio, including the v45 anchor, with rejected sessions
held in cash. All 300 frozen frontier records failed the standard, 18 bp, delay and neighborhood
gates. There were zero pre-factory-null survivors. Best OOS annualized returns were only about
17%-24%, so attractive isolated 2026 diagnostics were not used to rescue the direction.

## v1057-v1156 dynamic substitution

This campaign kept 100% of v45 on blocked sessions. On allowed sessions it substituted 2%-10% of
the anchor with a v247/v449 component mixture. Four prior-close multi-factor states, five
substitution weights, five component shares and four state quantiles produced 100 versions and 400
cells. Runtime was 6.44 seconds; cumulative comparison accounting reached 67,555 cells.

Of 300 frozen frontier records, 299 passed every economic pre-null gate. One failed historical
transfer and all 300 failed cumulative Bonferroni. The frozen lexicographic winner was v1102:

- normal sessions: 100% v45;
- supportive state sessions: 90% v45 plus 10% frozen v449/v60 component;
- prior-close state: SPY direction and risk-asset agreement positive, sector dispersion and SPY
  volatility negative;
- training-fitted state quantile: 30%, threshold `-0.3219912392580543`.

## Unified v1102 evidence

| Period or stress | Annualized return | MDD | IR | Total return |
|---|---:|---:|---:|---:|
| 2022-2023 training | 12.74% | 11.29% | 0.814 | 26.92% |
| 2024 | 14.14% | 11.66% | 0.800 | 14.14% |
| 2025 | 128.01% | 3.66% | 1.862 | 125.79% |
| 2024-2025 standard OOS | 60.99% | 11.66% | 1.423 | 157.71% |
| 2024-2025 at 18 bp | 56.12% | 11.99% | 1.327 | 142.46% |
| 2024-2025 with +5-minute delay | 57.73% | 14.93% | 1.359 | 147.45% |
| Consumed 2026 Q1 diagnostic | 51.12% | 0.75% | 2.289 | 10.51% |
| Consumed 2026 all diagnostic | 88.11% | 5.00% | 2.741 | 46.76% |
| Historical 2018-2020 | 1.13% | 17.93% | 0.226 | 2.54% |

All five chronological folds and all three start-date stresses were positive. v1158 tested 36
joint neighbors across substitution weight, v247/v449 share and state quantile; 36 passed versus
the frozen 70% threshold.

The v1157 routed-component null passed with 244 accepted entries. Observed profit was 0.8785,
above the session-permutation 95% threshold of 0.7313 and timestamp-shift 95% threshold of 0.6643.
Each family used 200 repetitions and seed 20260823. Evidence SHA-256 is
`94304f3ed1cc25f83aec140eade10cf8f172b02a2c5c65c0bda49edb5ff159a1`.

## Comparison and decision

Relative to v925, v1102 improves standard OOS annualized return by about 4.00 percentage points,
18 bp by 3.88 points, delay by 3.06 points, 2026 Q1 total by 1.11 points and 2026 total by 3.11
points. Its OOS MDD improves by about 0.20 points, while IR is about 0.037 lower.

Relative to v449, v1102 improves standard OOS by about 0.90 points, 18 bp by 0.55 points, delay by
0.77 points and historical annualized return by about 0.45 points. Its OOS MDD is about 0.07 points
worse, IR about 0.010 lower and consumed-2026 total about 0.69 points lower. It is therefore a new
Pareto alternative rather than a strict all-metric dominator.

The permanent inherited v45 factory-null failure and cumulative Bonferroni failure remain. v1102
is classified `USABLE_INHERITED_EXCEPTION_REVIEW`; Paper admission requires separate user
authorization.
