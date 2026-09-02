# v9505-v9604 multiclock residual results

- Status: `COMPLETE`
- Versions: 100/100
- New cells: 600
- Cumulative comparison cells: 284,383
- Frontier records: 300
- Pre-factory-null passes: 0
- Native-null runs: 0
- Paper changes: 0
- Runtime: 38.91 seconds

The three-clock, non-overlapping residual strategy family produced no admissible
candidate. Every frontier record failed the standard, 18 bp, extra-delay,
historical, neighborhood, and cumulative Bonferroni gates.

The best development result was `lev-v9597-fb785cab4cc2d74d`, with 39.09%
annualized return for the standard 9 bp scenario. It remained below the 50%
floor and its frozen all-2026 diagnostic was -13.52%, so it was rejected without
a native-null run or Paper admission.

The next unused version is v9605. Subsequent work must move to a genuinely
different state-conditional allocation or return source rather than tuning this
multiclock residual family.
