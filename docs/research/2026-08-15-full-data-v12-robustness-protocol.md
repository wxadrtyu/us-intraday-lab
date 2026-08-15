# Full-data intraday v12 robustness protocol

## Purpose

V12 follows the v11 full-universe search but removes 2026 from every ranking,
shortlist, beam, and target calculation.  Its purpose is to test whether sector
breadth and leadership can gate one long TQQQ/SOXL holding, or at most two
non-overlapping holdings, strongly enough to retain the 50% return target while
improving v11's doubled-cost and five-minute-delay failures.

This remains research only.  It cannot construct a broker, submit an order, or
modify any paper/live observation pool.

## Evidence partition

The primary source is the immutable, split-adjusted Alpaca IEX minute history.
Dataset IDs and content hashes are explicit in code and verified before read.

- 2021-2023: training and hypothesis screening;
- 2024: validation;
- 2025: development OOS;
- 2026-01-02 through 2026-08-12: consumed diagnostic only, attached after the
  2021-2025 frontier is frozen.

The separately labelled HF/Finnhub-derived 2018-2020 snapshots are not blended
with Alpaca.  After frontier freeze they are replayed as a cross-provider
historical-regime stress covering the late-2018 decline, 2019 transition, and
2020 crash/rebound.  Their `source-as-published; split-anomaly-gated` adjustment
label must remain visible in every result.

The user's new authorization permits strategy metrics on the previously blind
2026-04-01 through 2026-08-12 snapshot.  Because v11 already used 2026 in
shortlisting and target scoring, all 2026 observations are now consumed and
cannot be claimed as independent OOS in v12.

## Data-quality correction

Alpaca IEX minute histories are structurally valid but incomplete for some
symbols and sessions.  V11 accepted a five-minute bucket with four observed
minutes, so a missing boundary minute could silently shift an apparent bar open
or close.  V12 requires exact bucket boundaries:

- session open must contain the exact 09:30 New York minute;
- a completed decision bar must contain its exact final minute;
- entry and exit opens must contain the exact first minute of their buckets;
- no forward fill or interpolation is allowed.

This makes the extra-five-minute delay stress meaningful and prevents sparse
IEX prints from masquerading as scheduled fills.

After the strict-boundary run, a separately labelled diagnostic may allow at
most one minute of signal staleness and at most one minute between the scheduled
entry/exit boundary and the first observed IEX print.  It cannot override a
strict-run failure; it only distinguishes strategy weakness from sample loss
caused by IEX sparsity.  The same extra-five-minute delay stress still applies.

## Falsifiable hypotheses

1. **Sector-breadth-gated leveraged strength.** Buy the stronger of TQQQ and
   SOXL only when SPY is non-crashing, a sufficient fraction of sector ETFs is
   positive, and technology leadership confirms.  Otherwise hold cash.
2. **Dispersion contraction and breakout.** Relative strength is actionable
   only when sector dispersion is bounded and the selected leveraged ETF has a
   confirmed recent move, reducing false breakouts and delay sensitivity.
3. **Breadth-recovery reversal.** A leveraged ETF that has sold off from the
   open can be bought only after a causal six-bar recovery and improving sector
   breadth, targeting the weak-regime failure without using 2026 to choose it.
4. **Two-window complement.** If no single holding reaches the target, combine
   one morning and one afternoon sleeve only when their intervals do not
   overlap.  Maximum gross remains one and no session can exceed two round
   trips.

Each hypothesis is falsified if its development-ranked frontier cannot meet the
primary thresholds under both 18 bp and an extra five-minute bar, or if it
fails the frozen 2018-2020/2026 stress replays.

## Ranking and gates

Parameters are ranked on 2021-2025 only, lexicographically by the weakest
annualized return in 2021-2023, 2024, and 2025, followed by 2024-2025
annualized return and IR.  Neither 2018-2020 nor 2026 may affect shortlist size,
beam ordering, frontier selection, or parameter-neighborhood choice.

Standard execution pays 9 bp per round trip and enters at the next exact
five-minute bucket open.  Every frozen candidate receives:

- 9 bp and 18 bp scenarios;
- an additional exact five-minute-bar delay at 9 bp;
- 2021-2023, 2024, 2025, 2024-2025, 2018Q4, 2019, 2020, 2026Q1,
  2026 April-August, and 2026 all-period output;
- five contiguous development folds, start-date truncations, immediate
  parameter neighborhoods, trade counts, and family/portfolio trial counts;
- a multiple-comparison pressure disclosure.

The historical primary gate is annualized return at least 50%, MDD below 20%,
and IR at least 1 on 2024-2025, with positive returns in training, 2024, and
2025.  A future simulation-observation recommendation additionally requires
the same primary gate at 18 bp and with one-bar delay, at least four of five
positive folds, at least 70% passing immediate neighbors, positive aggregate
2018-2020 cross-source stress with MDD below 20%, and positive 2026 consumed
diagnostic with MDD below 20% and IR at least 1.  Even a complete pass requires
genuinely future sessions before promotion.

## Efficient execution

DuckDB loads each immutable snapshot once.  NumPy cubes cache exact-boundary
features.  Parameter cells are evaluated programmatically; fixed development
frontiers receive parallel cost/latency replays and atomic JSON checkpoints.
The final report records scan counts, runtime, and every failed gate.
