# Independent sector multifactor research: v1765-v1864

## Decision

Completed all 100 versions and 12,800 cells in 488.65 seconds (8 minutes 9 seconds), producing
300 frozen frontier records. Pre-null survivors: **0**. New admissions: **0**. All 300 records
are rejected. The active Paper execution pool remains the single previously authorized v1254;
none of these sector candidates is added, and no existing failure label is removed.

The strongest development-ranked candidate is `sector-v1837-ef36cd7aca0962bc`: sector rank,
inverse recent volatility ratio and return acceleration, with the orderly-market cash filter.
It is a falsification result, not a usable strategy. It fails return, IR, training-period,
fold, neighborhood, consumed-2026, independence and global comparison gates.

| Period / scenario | Annualized | MDD | IR | Total return |
|---|---:|---:|---:|---:|
| 2022-2023 training | -0.67% | 2.79% | -0.332 | -1.32% |
| 2024 | 0.30% | 0.29% | 0.719 | 0.30% |
| 2025 | 9.83% | 1.29% | 0.809 | 9.71% |
| 2024-2025, 9bp | 4.93% | 1.29% | 0.696 | 10.04% |
| 2024-2025, 18bp | 4.04% | 1.83% | 0.224 | 8.18% |
| 2024-2025, extra 5-minute delay | 3.89% | 1.29% | 0.609 | 7.89% |
| 2026Q1 consumed diagnostic | -0.65% | 0.33% | -3.427 | -0.16% |
| All available 2026 consumed diagnostic | -4.38% | 2.85% | -2.243 | -2.68% |
| 2018-2020 historical stress | 0.57% | 1.80% | -0.766 | 1.28% |

Only 19 active sessions occur in 2024-2025. Correlation with v1254 is 0.003 in 2024,
0.907 in 2025 and 0.867 in pooled 2024-2025, exceeding the 0.65 limit. Different instruments
and factor labels did not provide independent returns in the strongest case.

168/300 frontier records pass the correlation gate, but their best development-ranked record,
v1827, produces only 0.38% standard annualized return, 0.014% stress-floor annualized return,
and 0.36% consumed-2026 total return. Independence alone also does not establish usability.

### Overlapping rejection counts

| Gate failed | Records / 300 |
|---|---:|
| Standard economic primary | 300 |
| 18bp economic primary | 300 |
| Extra-bar delay economic primary | 300 |
| Parameter-neighborhood 70% primary | 300 |
| 2026Q1 total above 5% | 300 |
| All-2026 total above 5% | 300 |
| Global Bonferroni | 300 |
| Four positive folds, standard | 294 |
| Four positive folds in every scenario | 300 |
| All scenario/start-date combinations positive | 291 |
| Historical positive return and MDD below 20% | 285 |
| Independence from v1254 | 132 |

These counts overlap; they must not be summed. No candidate reaches native factory null, so
no null is run and none is represented as passed. The complete selected metrics and all 100
checkpoint hashes are in `research/results/2026-08-26-v1765-v1864-sector-rotation.json`.

## Contract and baselines

This batch follows the user-authorized consolidation of the Paper execution family to frozen
v1254. It does not blend v45, v247, v449, v798 or v1254 into a new candidate. Eleven unleveraged
sector ETFs compete for at most one intraday position, long only, gross at most one, flat
overnight. Execution timing in the existing Paper system is unchanged.

Preregistration commit: `dfad259`. Ten distinct economic/factor mechanisms, five holding
windows, and two state modes produce 100 independently identified versions. The parameter grid
contains 12,800 cells, conservatively raising cumulative comparison pressure from 97,005 to
109,805. Different exposure targets may collapse to identical realized portfolios at the gross
cap; these are still counted as trials, not advertised as independent discoveries.

Three or four factors are combined in every mechanism. New sector-only relative-return and
rank factors complement causal drawdown/rebound, flow, path efficiency, volatility contraction,
volume contraction and acceleration factors. Normalization, score thresholds and state
thresholds use 2022-2023 only. The frozen ranking is minimum 2024-2025 annualized return across
9bp, 18bp and one-extra-five-minute-bar delay; ties use worst drawdown, minimum IR and the
weakest standard development subperiod. The top three records per version freeze before
2018-2020 history or consumed 2026 results are attached.

2024-2025 is a repeatedly used development-validation interval, not fresh independent OOS.
All available 2026, including Q1 and April-August, is consumed diagnostic. Neither interval
selects parameters or factor signs. The existing standard/stress gates remain, and this batch
also requires absolute daily-return correlation with v1254 at most 0.65 in 2024, 2025 and
pooled 2024-2025. Q1 and all-2026 total-return gates are both above 5%.

Frozen v1254 reconstruction matches its recorded return, MDD and IR metrics across three cost/
delay scenarios and six periods within numerical tolerance. Cash has zero return. The
same-clock equal-weight sector diagnostic loses approximately 14.5%-16.6% annualized after 9bp
in 2024-2025. This basket is availability-conditioned on observed execution boundaries; it is
a descriptive comparator, not a proposed executable strategy or a hindsight-free admission.

## Factor audit and data limitations

The preregistered factor audit contains 70 factor/clock pairs (14 factors times five clocks),
each reported separately in 2022-2023, 2024 and 2025. Thirty pairs have the same IC sign in all
three periods. For example, bar-23 rebound-from-low IC is 0.0583, 0.1179 and 0.0693 respectively.
No factors were pruned or reversed after viewing these results. Positive pooled factor IC is
not evidence of sufficient net portfolio returns or independent market exposure.

Read-only coverage diagnostics at the bar-35 entry clock found an executable sector on
498/501 training sessions, 248/252 sessions in 2024, 246/249 in 2025 and 153/153 consumed-2026
sessions. Median executable sectors were 5, 5, 7 and 9 respectively. Thus full eleven-sector
coverage is not assumed; observed IEX coverage is incomplete. There is no price filling,
minute-provider splicing, or retry with newly acquired data. A failed candidate here rejects
this frozen implementation on the available source, not every possible sector strategy.

## Reproducibility and execution boundary

The scanner reads only the fixed manifest-identified existing sources through DuckDB, caches
NumPy factor arrays, evaluates historical cost/delay scenarios with three worker threads, and
writes atomic per-version checkpoints. Checkpoint reuse requires matching proposal/dependency
hashes, source identities, version identity and completion state. Native factory-null checks
are reserved for candidates passing the preregistered pre-null boundary; no failed candidate
receives a weaker replacement test.

Local detailed records: `artifacts/research/v1765_v1864/`, including all 300 frozen records,
factor audit, baseline replay and contract hashes. Publication includes a compact evidence
index and selected complete metrics; raw data, SQLite databases and generated checkpoints are
not committed. No broker is constructed by this scanner and no orders, strategy allocation or
execution schedules are changed by research.

Full-repository Ruff passed and pytest passed 879 tests in 71.38 seconds, with one upstream
websockets deprecation warning.

## Research implication

Do not continue expanding the same sector-ranking parameter grid on this evidence. Its best
returns are too small and too correlated with the retained family; the low-correlation subset
has almost no net edge. The next hypothesis should change the economic event and exposure:
for example, rare intraday failed-breakdown/flow-absorption events with independently frozen
cash-state exclusions, evaluated standalone before any blend. Recheck version reservations
after v1864, preregister the factor interaction and frequency budget, and retain all current
economic, cost, delay and multiplicity gates. This is a next research direction, not an
admission recommendation or a promise of profitability.
