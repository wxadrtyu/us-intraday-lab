# v7796-v7895 liquidity-absorption results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 100 / 100
- Runtime: 15.379 seconds
- Cumulative comparison cells: 256,766
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

The selective bar-12-to-23 liquidity-absorption sleeve materially improved
cost, delay, drawdown, and 2026 transfer relative to v7696-v7795. The
development-ranked record `lev-v7878-3bbec7c98ccd6776` returned 65.52%
annualized at standard cost with 13.98% MDD, IR 1.45, and 365 active sessions.
The delayed scenario passed its primary gate with 61.46% annualized, 14.84%
MDD, and IR 1.49. All 100 records passed both consumed-2026 gates; the closest
record returned 15.66% in 2026Q1 and 30.35% across consumed 2026.

The 18bp scenario remained just below its return threshold at 47.77%
annualized, despite 15.43% MDD and IR 1.09. Historical annualized returns were
26.58%, 13.27%, and 14.93%, with MDD of 21.81%, 23.28%, and 19.84%, so the
mandatory historical gate also failed. With no record passing the 18bp primary
or historical gate, the primary-neighborhood share was zero. The closest
record's cumulative statistic was `z=1.751`; the largest campaign z-score was
1.802, leaving Bonferroni at `p=1.0`.

Native factory null was not run. No candidate was admitted and no
simulated-observation or execution state was modified. The next unused strategy
version is v7896.
