# v7896-v7995 sparse liquidity-absorption results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 100 / 100
- Runtime: 15.002 seconds
- Cumulative comparison cells: 256,866
- Strict pre-factory-null passes: 0
- All-non-global-gate records: 3
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

Raising the fixed absorption sleeve's training activation threshold to 80%
repaired the cost, delay, historical, and neighborhood failures seen in the
preceding batch. Three records passed every mandatory gate except cumulative
Bonferroni. The strongest such record by z-score,
`lev-v7989-cad6a1f1e18025ac`, returned 70.76% annualized at standard cost with
13.24% MDD, IR 1.60, and 216 active sessions. Its 18bp and delayed annualized
returns were 56.51% and 66.98%, with MDD of 13.42% and 12.43% and IR of 1.31
and 1.65.

Historical annualized returns for that record were 29.98%, 19.11%, and 18.36%,
with MDD of 19.07%, 19.82%, and 17.10%. Consumed 2026Q1 and all-2026 standard
returns were 26.35% and 44.41%; the primary-neighborhood share was 100%.

Despite this broad transfer, the record had only `z=1.484` across 216 active
sessions. Cumulative Bonferroni therefore remained `p=1.0`; even the largest
campaign z-score was only 2.254. The global gate rejected every record, so
native factory null was not run. This is a research milestone, not an admitted
strategy. No simulated-observation or execution state was modified. The next
unused strategy version is v7996.
