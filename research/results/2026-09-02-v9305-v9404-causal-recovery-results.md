# v9305-v9404 causal recovery results

## Outcome

- Status: `COMPLETE`
- Versions completed: 100/100
- New parameter cells: 12,800
- Cumulative comparison cells: 270,983
- Frontier records evaluated: 300
- Pre-factory-null passes: 0
- Native factory-null runs: 0
- Research-admissible candidates: 0
- Paper-pool changes: 0
- Elapsed time: 471.04 seconds

The preregistered long-only intraday recovery hypothesis did not meet the
existing admission standard. No candidate was promoted or added to Paper.

## Best development result (rejected)

`lev-v9330-2a010cafa08064f6` traded the range-low recovery hypothesis from
decision bar 17, next-bar entry, to exit bar 29.

| Scenario | 2024-2025 annualized | MDD | IR |
|---|---:|---:|---:|
| 9 bp | 17.55% | 11.53% | 1.334 |
| 18 bp | 11.52% | 12.41% | 0.863 |
| Extra 5-minute delay, 9 bp | 7.93% | 16.64% | 0.642 |

Although its consumed diagnostics were positive (2026Q1 +6.68%, all 2026
+17.23%), those periods were not used for selection. The candidate failed the
50% development return floor, cost and delay primary gates, every historical
scenario (standard historical annualized -9.50%, MDD 26.39%), the fold gate,
the 70% neighborhood gate (0%), and cumulative Bonferroni (p=1.0).

## Batch rejection counts

Every one of the 300 frontier records failed the standard, 18 bp, historical,
neighborhood, and Bonferroni gates. All 300 also failed the extra-delay primary
gate. The result rejects this recovery family as a replacement strategy rather
than treating an attractive 2026 diagnostic as evidence.

The next unused research version is v9405.
