# August 28 loss diagnosis, execution fix, and v1966-v2265 optimization

## Outcome first

The August 28 v1254 Alpaca Paper session lost **$3,510.22 (-3.5142%)**, ending flat at
$96,376.40. Both component and anchor sleeves selected SOXL, producing gross-one exposure to one
triple-leveraged ETF. Component bought 134 shares at 116.26 and exited at 110.952985; anchor bought
704 at 116.23 and exited at 112.254033. This concentration and post-entry reversal—not transaction
cost—caused most of the loss.

The orders were also invalidly late. The entry window ended at 15:32 UTC, but the 75-day IEX fetch
returned later and orders were submitted around 15:40 UTC. The runner checked the deadline before
fetching but not after. This accidentally improved the buy prices and reduced the realized loss versus
the 9bp next-bar-open reference (-4.8271%); it is not favorable execution evidence.

Commit `965265a` adds a second deadline check after data/factor calculation and before any signal or
order preparation. A late result now appends `ENTRY_WINDOW_MISSED_AFTER_DATA` and stays in cash.
The two-minute boundary is unchanged. Seven targeted runner tests pass. No historical order was
altered, and no manual submit/cancel occurred.

## Why the risk overlays failed

- v1941 scored August 28 as normal and retained 90% gross. Positive SPY return and low volatility
  offset breadth of only 3/11 sectors. Its 9bp replay still lost 4.3444%.
- The loss arrived after entry. At the decision cutoff the leveraged-ETF momentum and market-health
  variables looked favorable. Both a trained downside model and a monotonic health score classified
  August 27/28 as normal.
- Same-symbol concentration was real, but it occurred on only 27 development sessions and was not
  the source of the historical worst drawdown. A cap reduces this incident without solving global MDD.

August 27 and 28 are consumed diagnostics only. No score, threshold, cap, model, or candidate was
ranked using their outcomes.

## Frozen campaigns

### v1966-v2065: strict-complete multifactor state plus concentration

100 unique hypotheses, 5.290 seconds. Missing any of 16 factors forced cash. Every cell improved
development MDD/tail substantially, but the best retained only 20.3% annualized return. August 28 had
two missing factor boundaries, so apparent avoidance was a matched-availability confound, not alpha.
Zero primary passes, zero admissions.

### v2066-v2165: train-only imputation and missing indicators

100 unique hypotheses, 5.295 seconds. At least 12/16 real factors were required; other values used
training-only medians plus missing flags. Five candidates passed all three primary return/MDD/IR gates.
Best-ranked v2153:

| Scenario | Annualized return | MDD | IR |
| --- | ---: | ---: | ---: |
| 9bp | 57.60% | 8.95% | 1.64 |
| 18bp | 52.69% | 9.28% | 1.52 |
| +5 minutes/9bp | 53.56% | 12.24% | 1.55 |

It failed risk improvement (tail only 6.8%-7.9%), historical 2018-2020 return (-0.29%), and global
Bonferroni. v2133 added an 85% same-symbol cap and would have reduced August 28 replay loss from
4.827% to 4.103%, but also failed tail, history, neighborhood, and global gates. Zero admissions.

### v2166-v2265: monotonic seven-factor health plus concentration

100 unique hypotheses, 5.378 seconds. Fourteen passed all three primary gates, but none passed the
20% MDD/15% tail-improvement requirement. Best-ranked v2248 produced 56.48% / 51.59% / 53.06%
annualized across standard/cost/delay, but only about 3%-4% tail improvement, negative historical
return (-2.49%), 22.5% historical MDD, and global failure. It did not flag August 28. Zero admissions.

As a mechanism diagnostic, a pure 40% same-symbol cap preserves 55.3%, 50.8%, and 50.7% annualized
returns and would have limited August 28 replay loss to about 1.93%. But development MDD reduction is
approximately zero, tail improvement is only 7.3%-8.9%, and historical return remains negative.
It therefore cannot be promoted merely because it helps the consumed incident.

## Decision and next hypothesis

Scanned **300 new real versions (v1966-v2265)**, 300 parameter cells, in 15.963 aggregate seconds.
All used 2022-2023 training and 2024-2025 OOS ranking, plus 9bp, 18bp, delay, starts, folds,
neighborhood, historical and global-comparison checks. No candidate passed all fixed gates. The Paper
pool remains v1254; no failed candidate was deployed.

The standalone recent-session factor extractor matched all 16 frozen research-cube factors on
2026-08-12 to 1e-12, including missing values, before evaluating consumed August 27/28 data.
The final repository suite passed **908 tests** in 72.37 seconds; repository-wide Ruff passed. The
only warning was the existing `websockets.legacy` deprecation warning.

Entry-state filters cannot reliably predict this post-entry reversal. The next preregistered campaign
should test causal post-entry invalidation/stop exits using only completed bars, next-bar execution,
explicit gap risk, and unchanged cost/latency stresses. It must prove broad MDD/tail improvement rather
than simply clipping August 28. Until such a candidate passes, the only production change is the
late-entry fail-closed fix.

G: was completely full during the work. To permit Git to write recoverably, only the rebuildable
`G:/us-intraday-lab/.mypy_cache` was moved to
`E:/codex-recoverable-cache/us-intraday-lab-mypy-cache-20260829`; no research data, database,
strategy artifact, or runtime evidence was deleted.
