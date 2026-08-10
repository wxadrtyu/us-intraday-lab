# TwelveData v2 final result and v3 candidate

## Decision

The frozen v2 regime ensemble is rejected and must not enter `paper_shadow`.
Its exact-2025 final test lost 7.47%, annualized to -7.61%, with 16.02% maximum
drawdown and 0.875 profit factor. The combined 2024-2025 evidence annualized
to 4.49%; annual return, drawdown, start-date, leave-one-symbol-out, and both
null-test gates failed.

The first v1 final access failed closed before signal evaluation because the
upstream `test.parquet` unexpectedly covered 2025-01-02 through 2026-08-07.
The v1 ledger remains consumed. A deterministic exact-2025 snapshot was sealed
before v2, bound to its parent and child SHA-256 hashes, and v2 was then consumed
exactly once.

## Data-contract findings

- `vix_level` changes scale materially across splits and is excluded from future
  strategy DSL candidates.
- The research universe grew from 37 symbols in train to 51 in 2025. Future
  proposals must freeze the exact symbol list instead of silently admitting new
  symbols during forward evaluation.
- Exact take-profit evaluation must use the first minute that crosses the limit
  and must exit the matched SPY benchmark at the same minute.

## Promising v3 family (not yet promoted)

The candidate is long-only and never exceeds 100% gross exposure.

1. At minute 45, select at most the strongest stock when it is above causal
   VWAP, has at least 1.5 relative cumulative volume, is at least 0.3% above its
   open, exceeds SPY by a bounded threshold, and sits high in its opening range.
2. Enter at minute 46, take profit at 2%, otherwise exit around minute 330.
3. If no stock qualifies, buy SPY only when the prior SPY RTH session was
   positive and current SPY return lies in a bounded positive interval; exit
   around minute 300-330.
4. Charge the frozen 1.5x round-trip cost of 9 bps.

A focused 1,458-point structural neighborhood produced 69 variants that kept
the 8% train floor and the combined OOS hard gates. A balanced representative
had train/2024/2025 annualized returns of 8.37%/11.27%/9.64%, and combined
2024-2025 annualized return 10.45%, matched-SPY IR 0.72, maximum drawdown 6.97%,
and profit factor 1.35. A higher-return neighbor produced 11.18% combined return,
IR 0.97, and 6.05% drawdown while retaining an 8.56% train return.

These are research results, not final evidence. No v3 parameters have been run
on the sealed 2026H1 interval.

## Next protocol

- Freeze a bounded 12-variant v3 neighborhood and a 51-symbol universe.
- Implement one common exact-minute evaluator for selection, final testing, and
  paper execution semantics.
- Require the unchanged hard gates, parameter stability, start-date stability,
  leave-one-symbol-out, and two 500-repetition null tests.
- Consume the sealed 2026H1 snapshot once. Promote only if every gate passes.

The sealed 2026H1 snapshot covers 123 sessions from 2026-01-02 through
2026-06-30 and has SHA-256
`f27fc6084780309b1563ac0b1fe48ae56991cf5cc5b604b259bf0669d9acb348`.

## v3 final result

The frozen v3 family is also rejected and must not enter `paper_shadow`.
The exact winner and its eight frozen survivors were evaluated on 2026H1 only
after their development metrics, ranking, parameters, universe, data bytes,
costs, and gates had been sealed. An initial access failed before the first
strategy evaluation because date-like values had incompatible Python types. A
separate, hash-bound recovery row documented that failure and the recovery run
was then consumed exactly once.

The isolated 2026H1 result made 4.20% over 123 sessions (8.80% annualized),
with -0.312 matched-SPY information ratio, 9.02% maximum drawdown, 1.307 profit
factor, and 46 trades. Its four time-fold annualized returns were 134.97%,
-6.86%, -23.17%, and -14.56%, showing that the gain was dominated by the first
part of the interval.

Combined 2024 through 2026H1 evidence remained superficially attractive at
11.22% annualized return, 0.819 information ratio, 1.388 profit factor, and 198
trades. It nevertheless failed the unchanged 8% drawdown ceiling at 9.02% and
also failed start-date stability, leave-one-symbol-out stability, parameter
stability, and the circular-shift null test. Only annual return, information
ratio, profit factor, trade count, walk-forward positivity, symbol
concentration, and the signal-permutation null test passed.

The immutable final evidence is stored under experiment
`portfolio-858a78f33c63bb041081b575d70863b0` with evidence SHA-256
`abbef22711fc2fa101a9b8fa22aa2ba0b1e9e3c48513275b3376c47464bbc326`.
The consumed 2026H1 observations are audit evidence only and must not be used
to tune another strategy family. The next family must be motivated and screened
from development data without adapting its rules to these final outcomes, and
it requires a genuinely new forward interval before promotion.
