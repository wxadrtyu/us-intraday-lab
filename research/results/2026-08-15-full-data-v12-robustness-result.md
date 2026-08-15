# Full-data intraday v12 robustness result

## Outcome

No candidate qualifies for simulation observation.  The exact-boundary search
found no standard-cost primary hit.  A diagnostic allowing at most one minute
of boundary staleness produced many 9 bp development hits, but none survived
the complete cost, latency, historical-regime, multiple-comparison, and
consumed-2026 gates.

The existing paper/live observation pools remain unchanged.  No broker was
constructed and no order route was touched.

## Correction to the v11 evidence boundary

V11 reported a 51.49% 2024-2025 annualized return and 20.85% total return in
2026 at 9 bp, but it explicitly used 2026 in sleeve shortlisting, beam/portfolio
scoring, and target-hit selection.  Its report correctly marked 2026 consumed.
V12 therefore removes 2026 from every ranking operation and uses it only after
the 2021-2025 frontier is frozen.

V11 also accepted a five-minute IEX bucket when four of five minutes were
present.  If the boundary minute was missing, the apparent open or close could
silently move.  V12's primary run requires the exact signal-close, entry-open,
and exit-open minutes.  A separate one-minute-tolerance run is diagnostic only
and cannot override a strict-run failure.

## Evidence contract

- Primary source: seven immutable, split-adjusted Alpaca IEX snapshots covering
  2021-01-04 through 2026-08-12.
- Ranking only: 2021-2023 train, 2024 validation, and 2025 development OOS.
- Consumed diagnostic only: 2026Q1, 2026 April-August, and 2026 aggregate.
- Cross-provider stress only: separately labelled HF/Finnhub-derived 2018Q4,
  2019, and 2020 snapshots.  They retain the
  `source-as-published; split-anomaly-gated` label and are never blended with
  Alpaca observations.
- Strategy constraints: long only, no overnight, gross at most one, cash when
  filters fail, one holding per session in the single scan and at most two
  non-overlapping round trips in the portfolio scan.

## Scan audit

| Run | Sleeve cells | Portfolio cells | Primary hits | Frontier | Runtime |
|---|---:|---:|---:|---:|---:|
| Exact boundaries | 74,844 | 0 | 0 | 76 | 64.83 s |
| One-minute tolerance diagnostic | 74,844 | 8,592 | 195 portfolios | 389 | 93.53 s |

Both runs used DuckDB snapshot loading, cached NumPy features, two parallel
pressure workers, and atomic JSON checkpoints.  The exact run retained 30
morning cells but zero afternoon cells after the minimum-trade and positive
2021-2023/2024/2025 requirements, so no honest exact-boundary two-window
portfolio existed.

Full generated evidence is stored locally at:

- `artifacts/accelerated_research/full-universe-intraday-v12-robustness.json`;
- `artifacts/accelerated_research/full-universe-intraday-v12-tolerance1.json`.

These remain ignored generated artifacts rather than committed market data.

## Exact-boundary result

The highest exact-boundary 2024-2025 return was
`lev-v12-e6eaa406f30d8bc0`, a single dispersion-breakout sleeve.  It made 93
development round trips.

| Segment/scenario | Annualized/total return | MDD | IR |
|---|---:|---:|---:|
| 2021-2023 train, 9 bp | 6.13% annualized | 7.32% | 0.74 |
| 2024, 9 bp | 8.50% annualized | — | — |
| 2025, 9 bp | 43.02% annualized | — | — |
| 2024-2025, 9 bp | 24.47% annualized | 11.07% | 1.05 |
| 2024-2025, 18 bp | 21.32% annualized | 11.80% | — |
| 2024-2025, extra 5-minute delay at 9 bp | 20.62% annualized | 13.18% | — |
| 2018-2020 cross-source stress | -18.07% annualized | 43.41% | — |
| consumed 2026 aggregate | 0.14% total | 20.99% | 0.01 |

The development-ranked leader had a more uniform 11.76%/11.94%/16.31% across
train/2024/2025 and 14.09% OOS, but it also failed 2018-2020 and had only 0.34%
total return with 0.20 IR in consumed 2026.  The strict result falsifies the
claim that exact-boundary, low-turnover breadth/dispersion signals can preserve
the requested 50% return with this IEX sample.

## One-minute-tolerance diagnostic

The strongest cost-stressed standard-cost hit was
`lev-v12p-99ccf325a4e379e8`.  It combines two non-overlapping
dispersion-breakout sleeves:

1. decision bar 17, entry bar 18, exit bar 41; risk return at least 1.6%, sector
   breadth at least 45%, sector dispersion at most 1.0%, SPY non-negative;
2. decision bar 41, entry bar 42, exit bar 72; risk return at least 0.3%, at
   least 0.6% over SPY, breadth at least 45%, dispersion at most 0.6%, and SPY
   at least -1.0%.

It had 188 active development sessions and 214 component round trips.

| Segment/scenario | Annualized/total return | MDD | IR |
|---|---:|---:|---:|
| 2021-2023 train, 9 bp | 12.24% annualized | 9.27% | 1.20 |
| 2024, 9 bp | 24.17% annualized | — | — |
| 2025, 9 bp | 101.23% annualized | — | — |
| 2024-2025, 9 bp | 57.84% annualized | 6.26% | 1.51 |
| 2024-2025, 18 bp | 48.40% annualized | 8.20% | 1.28 |
| 2024-2025, extra 5-minute delay at 9 bp | 42.50% annualized | 11.93% | 1.32 |
| 2018-2020 cross-source stress | -14.10% annualized | 39.41% | -1.27 |
| consumed 2026Q1 | -2.29% total | — | -0.40 |
| consumed 2026 April-August | 3.55% total | 5.37% | 0.67 |
| consumed 2026 aggregate | 1.17% total | 9.96% | 0.15 |

The result is dominated by 2025.  Four of five development folds were positive,
but the first fold lost 1.17% annualized with only three active sessions.  The
immediate-neighbor primary-pass fraction was 81.25%, while the 83,436-trial
Bonferroni p-value was 1.0.  It narrowly misses the 18 bp target, materially
misses the delay target, fails the historical cross-source stress, and fails the
consumed-2026 IR gate.

## Decision

All v12 variants remain research-only failures.  The one-minute diagnostic is
useful evidence that IEX sparsity explains part of the exact-run sample loss,
but relaxing the boundary does not solve the core instability: returns remain
2025-heavy, weak before 2024, negative across 2018-2020, and nearly flat in
consumed 2026 after costs.

No further parameter expansion on the same 2021-2026 observations is justified.
The next defensible step is prospective collection of exact executable quotes
or consolidated minute bars under a frozen v12 specification.  Existing 2026
data cannot be reused as a new final.

## Verification

- `python -m ruff format scripts/search_full_universe_intraday_v12_robustness.py`
- `python -m ruff check scripts/search_full_universe_intraday_v12_robustness.py`
- `python -m py_compile scripts/search_full_universe_intraday_v12_robustness.py`
- `git diff --check`
- `$env:PYTHONPATH=(Resolve-Path .\src).Path; python -m pytest --tb=short -ra`
  — 838 passed, one dependency deprecation warning, 53.73 seconds.

The explicit `PYTHONPATH` is required because the machine's editable install
still points at the separate `long-horizon-5min` worktree.  With the current
worktree selected, all tests pass.
