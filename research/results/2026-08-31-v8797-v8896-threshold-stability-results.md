# v8797-v8896 threshold-stability sparse-gap veto results

## Outcome

- Atomic campaign status: `COMPLETE`
- Economic versions / evaluated cells: 100 / 100
- Runtime: 14.485 seconds
- Cumulative comparison cells: 257,777
- Strict pre-factory-null passes: 0
- Native factory null runs: 0 (ineligible)
- Admissions or paper-pool changes: 0

The narrow stability scan moved the evidence frontier smoothly from the 20% to
the 19% veto quantile. `lev-v8820-8acae1579ad5e0b7` returned 118.52% annualized
at standard cost, IR 2.381, and 384 active sessions. Its 18bp and delayed
annualized returns were 98.79% and 102.49%; historical returns were
44.08%/31.60%/36.57%; consumed 2026Q1 and all-2026 returns were 9.90% and
19.97%; neighborhood share was 100%.

Every gate passed except the prospective z screen: z=2.939 versus z>=3.0.
Native factory null was not run. The next batch extends the symmetric quantile
block by one point and tests stronger ridge shrinkage. The next unused version
is v8897.
