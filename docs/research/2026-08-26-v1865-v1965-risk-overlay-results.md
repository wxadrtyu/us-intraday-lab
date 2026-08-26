# v1254 downside optimization and matched-availability falsification

## Outcome

Completed 100 risk-overlay versions (v1865-v1964), 1,200 parameter cells and 300 frozen
frontier records in 11.15 seconds. Eight initially passed the economic, stress and added
downside gates. A separate post-selection diagnostic, v1965, compared identical state-data
availability and invalidated seven of those eight risk-improvement claims. One remains a
research candidate: `risk-v1941-d230dcf6cfea997c`. **New admissions: zero.**

The current Paper pool remains frozen v1254. No runner, allocation, strategy parameter,
credential, scheduler trigger, ledger or order was changed. The entry task is Ready for its
unchanged 20:00 local start. New research does not replace tonight's executor.

## Yesterday's actual Paper loss

Read-only brokerage reconciliation for 2026-08-25 found 16 filled orders: eight entries and
eight exits. The account is flat with no open orders. SOXL entry notional was $87,224.34, about
87.22% of the original $100,000 account, across the former four strategy labels.

- SOXL fill-price realized PnL: -$835.31.
- TQQQ fill-price realized PnL: -$12.17.
- Total fill-price PnL: -$847.48; approximately 98.6% of that loss came from SOXL.
- Read-only account equity: $99,150.36. Its $849.64 decline from $100,000 differs from fill-price
  PnL by $2.16; fees or other account adjustments are not reconciled in this research report.

This was concentrated exposure to the same losing trade, not four independent sources of loss
or a failure to close positions. Consolidating names alone does not reduce concentration.
The historical scan stops at the existing source coverage through 2026-08-12; it does not
claim that any new rule would have avoided the actual 2026-08-25 loss.

## Frozen optimization contract

Preregistration commit: `37c7338`. Ten three/four-factor market-state hypotheses, two causal
state clocks (prior close and bar 17), and five distinct risk policies define 100 versions.
Within each version, four training-fitted state quantiles and three gross-budget caps form
12 parameter cells. No factor selection, threshold or ranking uses 2026 or yesterday's PnL.

Policies test whole-portfolio cash/half-budget, anchor-only cash/half-budget, and a lagged-loss
brake. The latter uses only the frozen baseline's preceding five completed sessions, never
the current session's PnL. All nonfinite required state inputs force cash. Entry and exit
clocks, the v45 anchor, and the v60 component are frozen.

The original 50% annualized / 20% MDD / 1 IR gates remain for 9bp, 18bp and one-extra-bar delay,
with positive development subperiods, four positive folds, start-date checks, 70% primary
parameter-neighborhood support, historical transfer, consumed-2026 diagnostics and global
multiple-comparison pressure. Added downside gates require at least 20% lower MDD and 15%
lower mean loss in the worst 5% of daily returns in all three scenarios. Global comparison
count is 111,005. Different parameter cells are not represented as independent strategies.

## Why the initial leading result was withdrawn

v1944 initially appeared to improve annualized return to 71.82% and MDD to 4.27%. Attribution
showed that 98.75% of its positive development return differences came from one date:
2024-08-07. Its required state was unavailable, so it held cash while the unfiltered baseline
lost 9.81% that day. It did not identify that loss through a successful economic forecast.
It changed no returns in the consumed-2026 interval.

v1965 was frozen in commit `3083539` after this issue was found. It is a stricter post-selection
falsification diagnostic, not independent OOS and not a newly discovered strategy. It applies
the identical finite-state cash mask to the baseline before comparing risk. Under this fair
comparison v1944's standard and 18bp MDD/tail improvements are zero. Its original records are
preserved, but the risk-improvement claim is withdrawn. Seven of eight candidates fail this
paired comparison; no failed record is promoted to a weaker substitute test.

## Remaining research candidate: v1941

The candidate combines current SPY return, SPY realized volatility, sector breadth and sector
dispersion at bar 17. A score below the frozen training threshold halves the risk budget.
The maximum gross budget is 0.90 in an allowed state and 0.45 in a weak state; underlying
volatility sizing can reduce actual investment further. Missing state forces cash.

### Fair 2024-2025 comparison

Both sides use the same state-data availability and unchanged execution clocks. The return
cost of lower risk is visible and must not be hidden by the unmatched original baseline.

| Scenario | Matched baseline annualized | Candidate annualized | Baseline MDD | Candidate MDD | Tail-loss reduction |
|---|---:|---:|---:|---:|---:|
| 9bp | 72.32% | 63.35% | 4.27% | 3.29% | 25.49% |
| 18bp | 66.86% | 59.28% | 4.47% | 3.39% | 25.68% |
| Extra 5-minute delay | 68.20% | 60.04% | 6.53% | 4.20% | 25.16% |

Relative MDD reductions are 22.82%, 24.22% and 35.67%, respectively. This is a risk/return
tradeoff, not a free improvement. The original unmatched v1254 has 63.60% annualized return
and 11.36% MDD, but that large MDD difference cannot all be attributed to the new risk rule.

### Candidate periods at 9bp

| Period | Annualized return | MDD | IR | Total return |
|---|---:|---:|---:|---:|
| 2022-2023 training | 9.77% | 9.87% | 0.722 | 20.37% |
| 2024 | 24.36% | 2.77% | 2.373 | 24.36% |
| 2025 | 115.26% | 3.29% | 1.902 | 113.31% |
| 2024-2025 reused development validation | 63.35% | 3.29% | 1.661 | 165.28% |
| Consumed 2026Q1 | 45.79% | 0.93% | 2.302 | 9.56% |
| All available consumed 2026 | 72.51% | 4.69% | 2.628 | 39.25% |
| Historical 2018-2020 | 0.0323% | 15.98% | 0.152 | 0.0724% |

The consumed-2026 total is lower than frozen v1254's 44.45%, although its MDD is lower. It is
not a new independent test. Historical return is almost zero, leaving little robustness margin.

## Admission decision and verification

The retained candidate still fails global Bonferroni (p=1.0 over 111,005 comparisons), inherits
the v45-null failure, and has no completed full-strategy native overlay null. Passing the paired
risk diagnostic does not waive any of these. Native validation remains pending for this one
research candidate; the seven paired-risk failures do not advance. No Paper or live admission
is recommended on current evidence.

Overlapping first-pass failures among 300 records include global comparison 300, historical
transfer 244, neighborhood 198, 18bp primary 155, delay primary 138, standard primary 137,
MDD-reduction 124, tail-reduction 107 and Q1 diagnostic 46. There are 292 first-pass economic/
risk rejections, seven additional paired-risk rejections, and one pending research candidate.
These are not 300 independently tested strategies.

Scripts use existing manifest-identified data, cached NumPy arrays, parallel pressure-scenario
metrics and atomic version checkpoints. All eight audit replays match their frozen metrics.
The publication JSON contains the selected complete metrics, paired-audit summaries, source
contract, 100 checkpoint hashes and sanitized Paper fill aggregates. Databases, raw data and
credentials are excluded from Git.

Full-repository Ruff passed. Pytest passed 886 tests in 69.61 seconds with one upstream
websockets deprecation warning. All 100 published checkpoint hashes were verified before
publication. No Paper execution source file changed in this optimization phase.

Next work should validate the full candidate's native null and fresh forward behavior, keeping
data-availability safeguards separate from economic alpha. A capital cap can mechanically
lower exposure, but neither yesterday's loss nor these repeatedly used historical samples
justify silently changing the running strategy.
