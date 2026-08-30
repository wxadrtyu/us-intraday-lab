# v7495-v7594 last-bar loss-veto results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 100 / 100
- Runtime: 20.798 seconds
- Cumulative comparison cells: 256,455
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

Moving the loss veto to bar 23 materially strengthened the economic frontier.
`lev-v7577-16febbbf5c8877e6` passed every non-global gate with 90.03% standard
annualized return, 10.45% MDD, IR 2.24 and 169 trades. The 18bp and delayed
scenarios returned 81.34% and 86.24% annualized with IR 2.06 and 2.33.
Historical annualized returns were 29.73%, 23.77%, and 21.49%; 2026Q1 and
all-2026 totals were 6.29% and 11.02%. Its neighborhood share was 100%.

The cumulative statistic was still only `z=1.834`, so Bonferroni remained
`p=1.0`. The mandatory global gate failed and native factory null was not run.
This is a research milestone, not an admitted strategy.

No simulated-observation pool or execution state was changed. The next unused
strategy version is v7595.
