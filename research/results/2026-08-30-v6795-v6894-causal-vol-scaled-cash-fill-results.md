# v6795-v6894 causal volatility-scaled cash-fill results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 100 / 100
- Runtime: 24.356 seconds
- Cumulative comparison cells: 255,755
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

The fixed 30% trailing-volatility target reduced return more than risk. The
closest record by passed gates, `lev-v6826-184cd73d5bb251ac`, produced 51.68%
standard annualized return, 16.42% MDD and IR 1.65, but the 18bp annualized
return fell to 45.47%. The delayed scenario remained at 53.87% annualized and
IR 1.78. Its 2026Q1 and all-2026 totals were 6.40% and 5.05%.

The candidate failed the 18bp primary, 70% neighborhood, and cumulative
Bonferroni gates (`z=1.175`, `p=1.0`). The overlay did not improve the global
evidence statistic and should not be extended by target-volatility tuning.

No candidate was admitted and the existing simulated-observation pool was not
modified. The next unused strategy version is v6895.
