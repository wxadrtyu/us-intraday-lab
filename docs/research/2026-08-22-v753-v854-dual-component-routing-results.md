# v753-v854 dual-component routing results

## Outcome

The 100-version v753-v852 campaign produced one frozen development winner:
`lev-v798-d0612cdc630bb224`. It is a usable inherited-exception research candidate, not an
independent alpha discovery and not a full hard-gate pass. No existing Paper strategy, schedule,
ledger or observation was changed.

v798 keeps 90% in the frozen v45 anchor and allocates 10% to the frozen v449/v60 component only
when a prior-session four-factor state score is above its training-fitted 20th percentile. The
state uses SPY direction, sector breadth, risk-asset agreement and inverse SPY volatility; the
strategy otherwise holds that 10% allocation in cash. It remains long-only, gross at most one and
flat overnight.

## Scan and validation boundary

- 100 versions: five component totals times five v247/v449 splits times four routing modes.
- 325 new cells, 66,319 cumulative comparison cells, 6.69 seconds.
- Ranking used 2022-2025 only. Historical 2018-2020 and consumed 2026 were attached after each
  frontier froze.
- 247 of 250 frozen frontier records passed every economic pre-null gate. All 250 failed cumulative
  Bonferroni; three also failed historical transfer.
- v853 ran 200 session-signal permutations and 200 session-safe timestamp shifts only after v798
  froze.
- v854 tested 36 joint neighbors across total component weight, v247/v449 split and state quantile.
  All 36 passed the full economic, cost, delay, historical and consumed-2026 cell gate.

## Unified v798 evidence

| Period or stress | Annualized return | MDD | IR | Total return |
|---|---:|---:|---:|---:|
| 2022-2023 training | 11.79% | 11.19% | 0.780 | 24.81% |
| 2024 | 14.43% | 10.95% | 0.831 | 14.43% |
| 2025 | 116.34% | 3.29% | 1.906 | 114.36% |
| 2024-2025 standard OOS | 57.04% | 10.95% | 1.463 | 145.30% |
| 2024-2025 at 18 bp | 52.30% | 11.30% | 1.357 | 130.79% |
| 2024-2025 with +5-minute delay | 54.58% | 14.20% | 1.406 | 137.72% |
| Consumed 2026 Q1 diagnostic | 44.11% | 0.76% | 2.211 | 9.25% |
| Consumed 2026 all diagnostic | 83.94% | 5.00% | 2.779 | 44.77% |
| Historical 2018-2020 | 0.59% | 16.98% | 0.196 | 1.34% |

All five chronological development folds were positive. Start-date stresses beginning in 2022,
2023 and 2024 were positive. The joint neighborhood pass share was 100%, above the frozen 70%
threshold.

The routed v449 component passed its native null:

- observed profit: 0.9418 across 274 accepted entries;
- session-signal permutation 95% threshold: 0.7039;
- session-safe timestamp-shift 95% threshold: 0.6306;
- evidence SHA-256: `cc607d644c3503d4cf72e49b6afab43a337bf7a9fd2a4bbd43a2d4ecc3b5e3b7`.

## Comparison and decision

Relative to v449, v798 gives up roughly 3.05 percentage points of standard OOS annualized return,
3.27 points at 18 bp, 2.38 points under delay, 1.25 points in consumed 2026 Q1 and 2.67 points in
consumed 2026 total. In exchange, OOS MDD improves by about 0.64 points, historical MDD improves by
about 1.29 points, and OOS IR improves from about 1.433 to 1.463.

This is a defensible lower-drawdown alternative configuration, but it is not clearly superior to
v449 and it reuses the same v60 component. It therefore remains `USABLE_INHERITED_EXCEPTION_REVIEW`
rather than being automatically added to the Alpaca Paper pool.

The permanent failed labels remain explicit:

- inherited v45 factory null: failed;
- cumulative Bonferroni across 66,319 cells: failed, adjusted p-value 1.0;
- independent-alpha classification: false.
