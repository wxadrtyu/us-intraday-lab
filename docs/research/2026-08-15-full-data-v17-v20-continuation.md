# Full-data intraday v17-v20 continuation

## Status

This stage did not find a candidate that passes the complete gate set. The
research goal remains open. No candidate in this report is eligible for paper
or simulation observation, and no observation-pool, broker, or order state was
read or changed.

All ranking and beam retention use only explicit 2022-2023 training, 2024, and
2025. Consumed 2026 is computed only after each frontier is frozen. Repeated
2026 inspection makes every reported 2026 result diagnostic rather than
independent OOS.

## Falsification results

| Stage | Hypothesis | Total trials | Seconds | Best frozen diagnostic |
|---|---|---:|---:|---|
| v17 | Fixed QQQ/TQQQ/SOXL/XLK/XLE state rules | 150,439 | 67.27 | 2026 10.72%; OOS 18.54% |
| v17b | Add short midday windows | 228,315 | 105.02 | 2026 16.71%; OOS 20.27%; stress rank 11.51% |
| v17c | Up to five sparse non-overlapping sleeves | 246,712 | 120.62 | 2026 9.84%; OOS 24.71%; stress rank 17.39% |
| v18 | Diverse train/2024/2025/OOS sleeve retention | 657,392 | 462.13 | 2026 -22.10%; OOS 38.23%; stress rank 25.38% |
| volume exploration | Twenty-day same-time relative-volume states | 1,784,172 | 309.28 | 2026 24.22%; OOS 20.99%; 18bp 14.81% |
| v19 | Map relative-volume confirmation to TQQQ/SOXL | 304,302 | 246.46 | 2026 12.39%; OOS 21.86%; 18bp 15.91% |
| v20 five-slot | Unified prior-5, fixed-state, and volume sources | 784,121 | 389.16 | 2026 32.23%; OOS 30.85%; 18bp 20.91% |
| v20 seven-slot | Finer sequential opportunity windows | 638,730 | 456.12 | 2026 17.52%; OOS 34.43%; 18bp 15.38% |

The trial count for the generic volume exploration includes 114,696 sleeve
cells and 1,669,476 non-overlapping portfolio combinations. It froze 3,000
portfolios before attaching 2026; 740 exceeded 20% in the consumed diagnostic.
This was the first new source with positive returns in training, 2024, 2025,
and consumed 2026, but its return magnitude was far below the 50% development
and doubled-cost gates.

The five-slot unified search froze 3,000 portfolios after 784,121 trials. It
produced 48 consumed-2026 returns above 20%, but zero complete candidates. Its
diagnostic maximum returned 32.23% in 2026 with 11.04% MDD and 2.24 IR. The same
portfolio returned only 30.85% annualized in 2024-2025 at 9 bp, 20.91% at 18
bp, and 25.96% with one additional five-minute entry delay. Its weakest
development-segment return was 19.80%.

The seven-slot layout increased the best frozen portfolio's standard OOS to
34.43% but reduced doubled-cost OOS to 15.38% and produced no consumed-2026
return above 20%. More short holding intervals increased cost sensitivity
rather than creating an independent edge.

## Additional falsification checks

- Replaying frozen v8 on the current strict Alpaca cube produced only 18.46%
  development OOS at 9 bp, 8.81% at 18 bp, and a negative 2025. The older
  66.24% evidence therefore does not transfer across the current provider and
  exact-boundary contract.
- A 1,300-cell causal trailing-return cash overlay could not lift the fixed
  v11 diagnostic base above an 8.45% weakest development return.
- A 100-cell causal intraday stop/take-profit budget produced consumed-2026
  returns as high as 29.10%, but training remained negative and stress OOS was
  only about 28%-31%.
- Eighteen NumPy KNN expanding-fit variants strongly fit 2022-2023 but turned
  negative in 2024. The nonlinear model route was stopped rather than expanded.
- All 31 non-empty weekday subsets were tested on the fixed volume diagnostic.
  The best development-ranked subset reached only 20.07% standard and 15.24%
  doubled-cost OOS, so calendar filtering cannot close the return gap.

## Interpretation

The experiments identify a real but modest relative-volume-confirmed momentum
source. It improves 2026 Q1 and has low drawdown and good delay behavior. It
does not generate enough return after doubled costs. Mapping the same signal to
leveraged ETFs, adding more windows, and combining it with price-only sources
all failed to lift the development and cost returns to 50%.

The evidence also rejects several tempting shortcuts:

- using a consumed v11 base because its 2026 number is attractive;
- treating a high 2026 diagnostic as a development pass;
- relying on older v8 metrics from a different provider contract;
- increasing model complexity after a nonlinear fit fails immediately in
  2024;
- increasing sleeve count when doubled-cost performance deteriorates.

The next independent research stage should not enlarge these price/volume
threshold grids. A materially new route is required, while keeping consumed
2026 outside ranking. Candidate-level historical, start-date, and parameter
neighborhood checks remain mandatory before any future observation
recommendation; the stage scanners fail closed until those final checks are
run.
