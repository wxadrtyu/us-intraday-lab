# Leveraged intraday v7-v9 research result

## Outcome

The standard-cost historical target has been reached, but no new strategy is
approved for automated paper shadow. The strongest honest candidate is v8,
which selects its overlay parameters using 2022-2025 only. It clears the target
at the standard nine-basis-point round-trip assumption, then fails the doubled
cost and one-extra-bar latency gates. The 2026Q1 period is already consumed and
cannot be reused as a sealed final.

## Candidate results

| Candidate | Evidence period | Annualized net return | Max drawdown | IR | Decision |
|---|---:|---:|---:|---:|---|
| v7 frozen base | 2024-2025 development OOS | 66.24% | 6.28% | 2.31 | Rejected by final |
| v7 frozen base | sealed 2026Q1 | -50.15% | 20.49% | -2.36 | Hard fail |
| v8 causal overlay | 2022-2023 train | 51.57% | 9.77% | 1.94 | Historical pass |
| v8 causal overlay | 2024-2025 development OOS | 66.24% | 6.28% | 2.31 | Historical pass |
| v8 causal overlay | aggregate through consumed 2026Q1 | 53.85% | 8.84% | 1.94 | Numeric target met |
| v8 causal overlay | consumed 2026Q1 only | -16.98% | 8.84% | -0.80 | Diagnostic fail |

The v8 overlay goes to cash unless the prior completed-session v7 return stream
has both a five-session compounded return of at least -5% and a twenty-session
compounded return of at least -10%. Its selected parameters are unchanged when
ranking excludes 2026Q1, so the overlay itself was not chosen using that period.

## Execution stress

| Scenario | Aggregate annualized return | Max drawdown | IR | Target pass |
|---|---:|---:|---:|---|
| 9 bp, next-bar open | 53.85% | 8.84% | 1.94 | Yes |
| 18 bp, next-bar open | 39.15% | 10.24% | 1.43 | No |
| 9 bp, one extra 5-minute bar delay | 23.51% | 10.89% | 1.21 | No |
| 18 bp plus one-bar delay | 12.85% | 10.40% | 0.61 | No |

This sensitivity is too large for promotion. The result remains useful as a
research frontier, not as evidence that a beginner should expect 50% live
returns.

## Independent v9 search

The v9 search added intraday rebound, gap-down rebound, prior-day rebound, and
cross-asset momentum sleeves. It evaluated 9,882 sleeves and 38,400 three-slot
portfolios in roughly fifteen seconds while keeping 2026Q1 out of ranking.

- Seven standard-cost portfolios passed annual return, drawdown, IR, and every
  development-segment drawdown gate.
- None passed the same target at doubled transaction cost.
- All seven were negative in the consumed 2026Q1 diagnostic.
- Additional one-bar-delay variants did not repair the regime failure.

## Lifecycle decision

v7 is rejected. v8 and v9 remain research-only candidates. Neither may create
a broker, submit an order, or enter automated paper shadow under the current
hard gates. The existing v4 research-shadow campaign is unchanged.

The next search should target lower turnover and different return sources, then
freeze against genuinely future sessions. Reusing 2026Q1 for another final
decision would convert research into curve fitting.
