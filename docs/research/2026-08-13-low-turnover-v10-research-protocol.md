# Low-turnover leveraged intraday v10 research protocol

## Purpose and decision boundary

This task searches for a long-only, no-overnight, maximum-gross-one return
source that is materially different from the v8/v9 opening and morning
momentum stack.  It may produce research candidates, but it cannot construct a
broker, submit an order, or modify the existing paper-shadow observation pool.

The 2026Q1 interval is consumed.  It is loaded only after development ranking
is complete and is a diagnostic veto, never a ranking feature or independent
out-of-sample claim.  No dataset created after this task's initial inventory is
eligible.

## Immutable data boundary

Only the following pre-existing content-addressed snapshots may be read:

| Role | Dataset | Content SHA-256 | Period |
|---|---|---|---|
| TQQQ/SOXL development | `hf-finnhub-5min-138ddc27bc3de530051d01e30087e449` | `b7c75247b26a0958777148946932de2b58f605343395ac0f38aba0a0dd8ba56b` | 2022-2025 |
| SPY development | `hf-finnhub-5min-b78802459222d4baef0985e726232461` | `31a2c567e20121a2055305d868786c91e6fdc12c0166ff29b1b76e46dda70211` | 2022-2025 |
| TQQQ/SOXL consumed diagnostic | `hf-finnhub-5min-50ac3b84b79898a4e0d4ee63cc4947dc` | `9eb2e4b91f2a6e1ab642710901efe234c556d107b6bf204bf62224e5bdd7aa01` | 2026Q1 plus overlap |
| SPY consumed diagnostic | `hf-finnhub-5min-28a0c165f75db0eadc0953192212663b` | `96bdda963eae00d77e609da72be182c376e2d789405f0978df7d0d27c6120181` | 2026Q1 plus overlap |

The scanner must verify these identities from each immutable manifest and must
name datasets explicitly.  It must not discover datasets through directory
globs.  This prevents a concurrent acquisition task from entering the study.

## Baselines and falsifiable hypotheses

The frozen v8 reference is 66.24% annualized return, 6.28% MDD, and 2.31 IR on
2024-2025 at 9 bp, but only -16.98% annualized in the consumed 2026Q1 diagnostic;
it also falls to 39.15% under 18 bp and 23.51% with one extra five-minute bar of
latency on its reported aggregate interval.  A v10 candidate is useful only if
it improves these failure modes, not merely the aggregate return.

The pre-specified hypotheses are:

1. **Failed-breakdown recovery:** after a material intraday low, a causal
   recovery plus a non-crashing SPY state predicts a later rebound.  Falsified
   if no development-ranked neighborhood survives cost and latency stress.
2. **Relative-laggard recovery:** the weaker leveraged ETF can mean-revert after
   positive short-horizon confirmation, while cash filters remove persistent
   downtrends.  Falsified by unstable years/folds or concentration in a narrow
   parameter cell.
3. **Volatility-contraction continuation:** relative strength is tradable only
   after recent range contraction and renewed breakout, reducing false
   breakouts and turnover.  Falsified if it retains v8/v9 latency sensitivity.
4. **Regime-selective rotation:** one cross-sectional choice held for a longer
   window, or cash, can retain gross-one exposure with at most one trade per
   session.  Falsified if the lower turnover cannot preserve the return target.

## Selection and stress contract

Candidates are ranked only on 2022-2025, lexicographically by weakest annualized
return across 2022-23, 2024, and 2025, then 2024-2025 annualized return and IR.
The standard model charges 9 bp round trip and fills at the next bar open.

Every reported frontier candidate receives the same table for 2022-23, 2024,
2025, and consumed 2026Q1 under:

- 9 bp, next-bar open;
- 18 bp, next-bar open;
- 9 bp, one additional five-minute bar delay;
- start-date truncations at 2022-07-01, 2023-01-01, and 2024-01-01;
- contiguous time folds and calendar half-year folds;
- immediate parameter neighbors;
- multiple-comparison pressure based on family trial counts and a block
  bootstrap/null maximum over the development frontier.

The primary historical gate is annualized return at least 50%, MDD below 20%,
and IR at least 1 on 2024-2025, with positive returns in training, 2024, and
2025.  A simulation-observation recommendation additionally requires the same
primary thresholds under 18 bp and one-bar delay, at least four of five positive
development folds, stable start dates and parameter neighbors, and a positive
2026Q1 diagnostic with MDD below 20%.  Because 2026Q1 is consumed, passing that
veto still cannot create an independent-OOS claim; it only permits a future
prospective observation recommendation.

## Efficient execution and audit trail

The implementation will load each snapshot once through DuckDB, cache dense
NumPy cubes, vectorize parameter cells in bounded batches, and write atomic JSON
checkpoints.  The final artifact records family and portfolio trial counts,
wall-clock time, cache identity, selection masks, and all stress outcomes.
