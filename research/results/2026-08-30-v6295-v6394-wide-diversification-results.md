# v6295-v6394 wide-diversification results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 100 / 100
- Runtime: 288.957 seconds after nested-selection caching
- Cumulative comparison cells: 255,255
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

Broadening the same-clock parent ensemble from the previously tested 2-6
components to 8-20 components reduced concentration and increased the evidence
count, but diluted return below the hard 50% annualized floor. The record with
the largest number of passed gates, `lev-v6342-91b9241fad9709ce`, used 12
inverse-volatility-weighted parents and produced 2024-2025 annualized return
32.92%, MDD 7.41%, IR 1.49, 465 component trades, 2026Q1 total return 5.71%,
and all-2026 total return 18.80%. Its cumulative statistic improved to
`z=2.021`, but Bonferroni remained `p=1.0`.

All 100 records failed the 18bp, extra-five-minute, historical, neighborhood,
and cumulative Bonferroni gates; 86 also failed the standard primary gate.
This wide same-clock diversification mechanism should not be extended through
additional breadth tuning.

No candidate was admitted and the existing simulated-observation pool was not
modified. The next unused strategy version is v6395.
