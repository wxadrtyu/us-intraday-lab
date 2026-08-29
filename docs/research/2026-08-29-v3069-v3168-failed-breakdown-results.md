# v3069-v3168 independent failed-breakdown research

## Decision

The 100-version, 12,800-cell campaign completed in 160.86 seconds. It froze 300 frontier records
and produced zero pre-factory-null survivors. No candidate is admitted and no native null is run.
The approved v2968 risk candidate and the existing v1254 Paper pool are unchanged.

The campaign tested ten four-factor failed-breakdown, flow-absorption, range-recovery,
volatility-compression and relative-laggard mechanisms over five afternoon schedules, both
unfiltered and behind a training-fitted orderly-rebound cash state. All entries were next-bar,
all strategies were long-only with gross at most one and flat overnight, and all cells included
9 bp, 18 bp and one-extra-five-minute-bar latency scenarios.

## Strongest record

`lev-v3122-014523cde1378125` was the maximum-standard-return record. It combined session drawdown,
recent volatility contraction, return acceleration and path efficiency at bar 47, entered at the
next bar and exited at bar 59 behind the orderly-rebound state filter.

| Scenario / period | Annualized | MDD | IR | Total return |
|---|---:|---:|---:|---:|
| 2024-2025, 9 bp | 17.13% | 4.42% | 1.072 | 36.93% |
| 2024-2025, 18 bp | 13.38% | 5.54% | 0.819 | 28.36% |
| 2024-2025, +5-minute delay | 9.46% | 4.18% | 0.894 | 19.69% |
| 2018-2020 history | -4.34% | 19.44% | -0.831 | -9.45% |
| consumed 2026Q1 diagnostic | — | 3.37% | 1.247 | 2.95% |
| consumed all-2026 diagnostic | -3.69% | 7.22% | -0.493 | -2.26% |

Its parameter-neighborhood primary share is zero. It fails standard, 18 bp, delay, historical
15% return, Q1, all-2026, neighborhood and global comparison gates.

## Gate audit

Across all 300 frozen records, none passed the standard primary gate, 18 bp primary gate,
extra-bar-delay primary gate, historical 15% annualized-return gate, 70% neighborhood gate or
cumulative Bonferroni gate. Ninety-three records passed the four-of-five positive-fold gate,
69 exceeded +5% in consumed 2026Q1 and 18 exceeded +5% in all consumed 2026, but those isolated
diagnostics cannot rescue failed development and history.

The result falsifies this implementation of rare afternoon failed-breakdown recovery. Extending
its score thresholds or adjacent afternoon clocks would be parameter refinement of a weak source,
not a new hypothesis. The next independent direction should change the payoff driver, for example
cross-sectional leverage residuals between TQQQ/QQQ and SOXL/XLK with a causal dispersion trigger,
rather than another rebound-path score.

Atomic checkpoints and the complete summary remain under
`artifacts/research/v3069_v3168_failed_breakdown/`. Generated artifacts are ignored; the frozen
proposal, implementation and compact report are versioned. No broker, Paper allocation, submit or
cancel path was used.

Full-repository Ruff passed and pytest passed 935 tests in 57.61 seconds. The sole warning is the
existing upstream `websockets.legacy` deprecation.
