# Low-turnover leveraged intraday v10 stage result

## Outcome

No candidate qualifies for simulation observation.  The study found cleaner
drawdown and information-ratio profiles at lower turnover, but it did not find
a return source that simultaneously reaches the 50% standard-cost target,
survives 18 bp and one extra five-minute bar, and improves the consumed 2026Q1
weak-market interval.  The existing observation pool is unchanged.

This is a falsification result, not an independent final test.  The 2026Q1
interval had already been consumed by v7-v9 and was attached only after each
2022-2025 frontier was frozen.  It is a diagnostic veto and was never used for
parameter ranking.

## Data and execution boundary

The scripts accepted only four explicitly named immutable datasets and verified
their manifest content hashes before loading:

- TQQQ/SOXL development: `hf-finnhub-5min-138ddc27bc3de530051d01e30087e449`
  (`b7c75247...ba56b`), 2022-2025;
- SPY development: `hf-finnhub-5min-b78802459222d4baef0985e726232461`
  (`31a2c567...70211`), 2022-2025;
- TQQQ/SOXL consumed diagnostic:
  `hf-finnhub-5min-50ac3b84b79898a4e0d4ee63cc4947dc`
  (`9eb2e4b9...aa01`), 2026Q1 plus overlap;
- SPY consumed diagnostic: `hf-finnhub-5min-28a0c165f75db0eadc0953192212663b`
  (`96bdda96...0181`), 2026Q1 plus overlap.

There was no dataset discovery glob, download, broker construction, order
submission, overnight position, short position, leverage above gross one, or
write to the paper-shadow state.  This prevents another acquisition task's new
blind data from entering the study.

## Baseline and hypotheses

The reference v8 result annualized at 66.24% with 6.28% MDD and 2.31 IR on
2024-2025 at 9 bp, but its consumed 2026Q1 diagnostic was -16.98%.  Its reported
aggregate result fell to 39.15% at 18 bp and 23.51% with one extra bar.  V9
found seven standard-cost portfolio hits, none survived doubled cost, and all
seven were negative in consumed 2026Q1.

V10 tested four pre-specified alternatives: failed-breakdown recovery,
relative-laggard recovery, volatility-contraction relative breakout, and
regime-selective cross-sectional rotation.  The single-sleeve stage allowed at
most one trade per session.  The follow-up combined a non-overlapping morning
and afternoon sleeve, at most two trades per session and never more than gross
one.

## Scan audit

| Stage | Parameter cells | Portfolio cells | Frozen frontier | Runtime | Pressure workers |
|---|---:|---:|---:|---:|---:|
| Single sleeve | 35,100 | 0 | 324 | 39.03 s | 2 |
| Non-overlapping portfolio | 28,080 | 3,440 | 200 | 49.26 s | 2 |

The implementation loads the content-addressed snapshots once with DuckDB,
uses dense NumPy cubes for signal and return calculations, evaluates 18 bp and
latency scenarios in parallel, and writes each full checkpoint atomically.  The
two full local evidence files are
`artifacts/accelerated_research/low-turnover-intraday-v10.json` and
`artifacts/accelerated_research/low-turnover-intraday-v10-portfolios.json`;
they remain ignored generated artifacts rather than repository data.

Neither stage produced a 2022-2025 standard-cost primary-gate hit before the
frontier limit.  Therefore the conclusion does not depend on the 2026Q1 veto.

## Closest single sleeve

The highest 2024-2025 return among the frozen single-sleeve frontier was
`lev-v10-2cc705f8fd44b1cc`, a relative-laggard recovery trade decided after bar
23 and held to bar 77.  It requires the weaker ETF to trail by at least 0.3%,
have non-negative six-bar confirmation, remain above -2.5% from the open, and
pass causal SPY current/prior-session floors.

| Segment/scenario | Annualized return | MDD | IR |
|---|---:|---:|---:|
| 2022-23 train, 9 bp | 19.40% | 25.79% | 0.68 |
| 2024, 9 bp | 30.25% | — | — |
| 2025, 9 bp | 60.64% | — | — |
| 2024-2025, 9 bp | 45.03% | 8.56% | 1.06 |
| 2024-2025, 18 bp | 33.57% | 11.32% | 0.81 |
| 2024-2025, 9 bp plus one bar | 45.77% | 7.89% | 1.08 |
| consumed 2026Q1 diagnostic | -50.06% | 15.24% | -4.49 |

It made 346 development trades.  All five development folds were positive,
but the weakest fold annualized at only 1.52%, the 2022-07 and 2023-01 start
truncations had 23.24% MDD, only one of twelve immediate neighbors met the
primary return gate, and the family-trial Bonferroni p-value was 1.0.  It fails
the return, drawdown-neighborhood, doubled-cost, multiple-comparison, and
consumed-diagnostic requirements.

The strongest consumed-2026Q1 single-sleeve diagnostic was
`lev-v10-2f9093fed237177c`, a contraction breakout with 80.59% annualized
diagnostic return.  It is not a candidate: 2022-23/2024/2025 annualized returns
were only 6.82%/5.95%/22.23%, 2024-2025 IR was 0.64, and there were only 95
development trades.  Reporting it separately avoids hiding a weak-market
success inside aggregate ranking, while refusing to select it using the
consumed interval.

## Best non-overlapping portfolio

The development-ranked portfolio frontier leader was
`lev-v10p-7366e2b90e022efa`: an early regime-selective relative-strength sleeve
from bars 24-47 followed by a relative-laggard recovery sleeve from bars 48-77.

| Segment/scenario | Annualized return | MDD | IR |
|---|---:|---:|---:|
| 2022-23 train, 9 bp | 36.94% | 10.39% | 1.44 |
| 2024, 9 bp | 29.39% | 8.26% | 2.01 |
| 2025, 9 bp | 25.33% | 6.92% | 1.26 |
| 2024-2025, 9 bp | 27.29% | 8.26% | 1.58 |
| 2024-2025, 18 bp | 14.64% | 10.01% | 0.77 |
| 2024-2025, 9 bp plus one bar | 23.11% | 7.85% | 1.51 |
| consumed 2026Q1 diagnostic | -27.36% | 10.08% | -2.40 |

It made 443 development round trips.  All five folds and all three start-date
truncations were positive, but no immediate neighbor reached the 50% primary
gate and its 31,520-trial Bonferroni p-value was 1.0.  Lower turnover improved
IR and drawdown but did not supply enough net return; costs and weak-market
behavior remained decisive failures.

## Decision and next boundary

All v10 and v10p variants remain rejected research cells.  None should be added
to simulation observation, used to create a broker, or used to submit an order.
There is no modification to the existing v4 observation campaign or any other
current strategy pool.

The useful causal finding is narrower: late contraction breakouts can behave
well in the consumed weak interval, while laggard recovery improves historical
return, but the two properties do not coexist robustly in the available
TQQQ/SOXL universe.  Further parameter expansion on the same consumed history
would increase selection pressure without creating new evidence.  A future
research stage should wait for genuinely new sessions or use a pre-existing,
task-start allow-listed broader sector universe with a separately frozen
contract; it must not reuse 2026Q1 as a final.

## Verification

- `python -m pytest --tb=short -ra`: 826 passed, one third-party deprecation
  warning, 67.92 seconds.
- `python -m ruff check`: passed for both new scanners.
- `python -m py_compile`: passed for both new scanners.
- `git diff --check`: passed.
