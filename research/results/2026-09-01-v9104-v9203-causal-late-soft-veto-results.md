# v9104-v9203 causal late soft-veto results

## Outcome

- Campaign status: `COMPLETE`
- Causal versions / evaluated cells: 100 / 100
- Gate decision / earliest entry: bar 23 / bar 24
- Retrospective opening sleeve: excluded
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Paper-pool changes: 0

The execution-parity audit found that v9022, v9083, and their v9100 merge
scaled a route containing a bar-3-to-11 opening trade with information first
available at bar 23. That exposure cannot be known when the opening order is
placed, so their earlier research admissions are revoked as noncausal.

The preregistered repair applied the bar-23 soft veto only to the late route
entered at bar 24. None of 100 fixed factor, quantile, and ridge cells passed
the complete gate set. The closest candidate, `lev-v9192-210e7e5a556b677a`,
had 79.75% standard annualized return, 9.60% MDD, and 2.127 IR, but failed the
prospective evidence gate (z=2.784) and the consumed 2026 Q1 diagnostic
(+2.45%). Across all cells, the prospective z gate failed 100/100 and the
2026 Q1 diagnostic failed 86/100.

The user-requested four-way 25% allocation is recorded but not activated.
Only v1254 remains active because it is the sole member with a causal,
parity-verified forward evaluator. The next unused version is v9204.
