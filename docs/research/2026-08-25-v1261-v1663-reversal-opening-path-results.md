# v1261-v1663 reversal, opening-gap and intraday-path results

## Decision

No new strategy is admitted from this stage. The existing Alpaca Paper pool remains unchanged.
The best new standalone path rule failed the economic and transfer gates, while the best routed
path candidate failed its preregistered component-native null. Attractive aggregate returns from
the routed campaign remain attributable primarily to the inherited v45 anchor and frozen v60
component.

## Research boundary

- Ranking used 2022-2025 only. Consumed 2026Q1 and the rest of consumed 2026 were diagnostics and
  never selected factors, signs, clocks, thresholds or candidates.
- All strategies were long-only, gross at most one and flat overnight.
- Standard execution used 9 bp round-trip cost and next-bar entry. Stress checks used 18 bp and an
  additional five-minute bar of entry latency.
- The separate 2018-2020 source, chronological folds, start-date checks, parameter neighborhoods
  and cumulative multiple-comparison reference were retained.
- No Paper member, allocation, broker task or order route was changed by this research stage.

## Scan inventory

| Stage | Versions | New cells | Recorded elapsed | Outcome |
|---|---:|---:|---:|---|
| Stress-state reversal substitution | v1261-v1360 | 400 | 7.49 s | v1315 frozen, then rejected by v1361 null |
| v1315 native null and neighborhood | v1361-v1362 | 200 null repetitions + 36 neighbors | checkpointed | null failed; 36/36 neighbors passed |
| Opening-gap multifactor | v1363-v1462 | 12,800 | 145.84 s | 0 pre-null survivors |
| Intraday-path multifactor | v1463-v1562 | 12,800 | 187.13 s | 0 pre-null survivors |
| Routed path component | v1563-v1662 | 400 | 7.84 s | 274 pre-null survivors; all Bonferroni failures |
| v1589 routed path null | v1663 | 200 null repetitions | 4.52 s | failed; conditional v1664 not run |

The three vectorized search campaigns after v1362 evaluated 26,000 new cells. Including the
v1261-v1360 campaign, this stage evaluated 26,400 search cells plus two 200-repetition native
nulls and one 36-cell joint neighborhood. The cumulative comparison reference reached 94,355.
Per-version JSON checkpoints were written atomically. A transient Windows destination lock during
the opening-gap scan left all completed checkpoints intact; bounded atomic-replace retry was added
and the same preregistered campaign resumed without changing version identity or ranking.

## v1315 reversal substitution

`lev-v1315-b6edb535dc9901a6` kept 98% in v45 and routed 2% to v580 reversal during a bar-17 broad
selloff state. It reported 60.48% standard OOS annualized return, 56.37% at 18 bp, 57.16% with the
extra bar delay, 12.13% OOS drawdown, 1.410 OOS IR, 11.07% consumed-2026Q1 total return and 47.93%
consumed-2026 total return. Its 36-cell joint neighborhood passed in every cell.

The required routed reversal null nevertheless failed. Observed profit was 0.5087 versus 0.5417
for the session-permutation 95th percentile and 0.5380 for the safe timestamp-shift percentile.
Therefore v1315 is rejected and was not added to Paper.

## Opening-gap multifactor

Ten opening-gap, VWAP, relative-strength, flow, rank, path and volatility families were crossed
with five early schedules and unfiltered versus orderly-rebound cash states. All 300 frozen
frontier records failed the standard, 18 bp, delay, neighborhood and cumulative-Bonferroni gates.
Only 166 records exceeded 5% in consumed 2026. Several large 2026 diagnostics coincided with weak
or negative 2024-2025 performance, so none was promoted.

## Intraday-path multifactor

Six new causal factors were added: drawdown from the session high, rebound from the low, intraday
range position, recent volatility ratio, recent volume ratio and return acceleration. Ten
three-factor mechanisms were crossed with five midday/afternoon schedules and two state modes.
Again, none of the 300 frozen frontier records passed the standard, cost, delay, neighborhood and
Bonferroni gates. Only 71 records exceeded the consumed-2026 5% diagnostic threshold; 23 retained
positive history under the required drawdown ceiling.

The highest 2024-2025-return record, `lev-v1500-7374c951787a0721`, was explicitly retained only as
a rejected component experiment. Its 33.88% OOS annualized return came from -0.68% in 2024 and
81.11% in 2025; training annualized return was -1.38%, historical annualized return was -18.83%
with 43.39% drawdown, and its primary-neighborhood share was zero.

## Routed path component and v1589

The routed scan substituted 2%-10% of v45 only in frozen stress states, splitting that weight
between rejected v1500 and frozen v60. The unconstrained development leader assigned zero weight
to v1500, which is direct evidence that the new path source did not drive the best aggregate
result.

Requiring strictly positive path weight froze `lev-v1589-cdec7ceb171c7587`: 98% v45, 0.5% v1500
and 1.5% v60 in the prior-close defensive state. Its diagnostics were:

| Metric | Result |
|---|---:|
| 2022-2023 annualized return | 10.08% |
| 2024 annualized return | 13.60% |
| 2025 annualized return | 127.01% |
| 2024-2025 annualized / MDD / IR | 60.25% / 11.95% / 1.416 |
| 18 bp annualized return | 56.07% |
| Additional five-minute delay annualized return | 56.90% |
| Consumed 2026Q1 total return | 10.95% |
| Consumed 2026 total return | 48.24% |
| Historical annualized / MDD | 1.30% / 17.91% |
| Local primary-neighborhood share | 100% |

The v1663 native null evaluated the v1500 component only inside v1589's allowed state sessions.
Observed profit was 0.4989 from 173 accepted entries. It failed both the session-signal permutation
95th percentile of 0.6167 and the session-safe timestamp-shift percentile of 0.5730. Evidence hash:
`a28b8f7fa24ae5ab5092ef33cd31e3c74d2d0dd60868e18af53320d739adea30`.

The preregistered decision rule therefore rejects v1589 and skips conditional v1664. The inherited
v45 factory-null and global Bonferroni failures also remain explicit.

## Next falsifiable direction

The evidence argues against further tuning of fixed-clock opening gaps or the tested path-turn
component. A subsequent preregistered stage should move to a genuinely different opportunity set:
sector-ETF rotation with lower volatility targets and explicit cash states, or event-triggered
state transitions whose decision time is causal rather than another fixed-bar neighborhood. Any
such stage must preserve the same 2026 diagnostic boundary and cumulative comparison count.

## Revision log

- 2026-08-25: initial complete v1261-v1663 stage report.
