# v6695-v6794 state-gated wide-fill results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 100 / 100
- Runtime: 15.666 seconds
- Cumulative comparison cells: 255,655
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

Prior-close state gating repaired the historical and weak-market damage from the
ungated wide fill. Candidate `lev-v6776-f28d61d0cb13f09d` passed every frozen
economic, cost, latency, historical, fold, start-date, neighborhood, and
consumed-2026 gate. It produced 80.76% standard annualized return, 15.35% MDD,
IR 1.93, 71.15% at 18bp, 79.22% with an extra five-minute delay, 23.30%
historical delayed annualized return, 5.72% in 2026Q1, and 11.46% in all 2026.

Its cumulative z statistic was only 1.694 and Bonferroni p remained 1.0, so it
was not eligible for native factory null or admission. The next campaign should
target causal variance reduction or genuinely independent non-overlapping
return components, not tune this state threshold. The next unused version is
v6795.
