# v7595 loss-veto model-ensemble results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / neighborhood cells: 1 / 11
- Runtime: 20.073 seconds
- Cumulative comparison cells: 256,466
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

Equal-gross averaging across one development-ranked veto model from each of ten
economic factor families remained robust but did not improve the global test.
`lev-v7595-c67e347bbccbe1b9` produced 70.69% standard annualized return, 10.54%
MDD and IR 2.01. The 18bp and delayed scenarios returned 63.41% and 68.05%
annualized; historical annualized returns were 28.20%, 22.64%, and 22.00%;
2026Q1 and all-2026 totals were 6.12% and 13.50%. All eleven full and
leave-one-family-out cells passed the primary scenario gates.

The engine's evidence count is the number of active sessions, not the number of
concurrent model components, so the ensemble correctly retained 194 trades and
did not inflate evidence by summing correlated model votes. Its `z=1.762` and
Bonferroni `p=1.0` failed the mandatory global gate. Native null was therefore
not run.

No candidate was admitted and the existing simulated-observation pool was not
modified. The next unused strategy version is v7596.
