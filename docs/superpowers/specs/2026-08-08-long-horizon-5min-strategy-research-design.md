# Long-Horizon 5-Minute Strategy Research Design

Design decision: selected under the user's standing instruction to continue
research autonomously without lowering gates.

## Purpose

Extend the long-only US intraday strategy factory with a separate, auditable
five-minute research lane that can establish a more credible return and
information-ratio claim than the current 57-session one-minute archive.

The lane must find a strategy that:

- remains long-only and paper-only;
- preserves every existing historical hard gate;
- produces at least 10% annualized return after the existing 1.5-times cost
  sensitivity;
- achieves an out-of-sample information ratio of at least 0.5 versus QQQ;
- uses at least 90 chronological OOS sessions;
- reaches `paper_shadow` only after all gates pass.

Historical performance is not a promise of future profit. No real-money order
path is added or enabled by this work.

## Current Evidence and Constraint

The accepted one-minute snapshot contains 63 symbols but only 57 contiguous
2026 sessions for the production ETFs. Its current 17-session combined OOS
return is 1.11%, or 0.74% after the 1.5-times cost sensitivity. Annualizing
that short interval gives about 11.5% after costs, but the interval is too
short and its IR versus SPY is only about 0.25.

The legacy archive also contains AAPL and QQQ five-minute bars from 2025-01-02
through 2026-07-02. This gives roughly eighteen calendar months without a new
data purchase and supports a substantially longer chronological holdout.

## Chosen Approach

Create an isolated `5min_long_horizon` research lane for AAPL and QQQ. Do not
replace or mutate the accepted one-minute dataset, its strategies, or its
registry evidence.

The alternatives were rejected for this iteration:

1. Further tuning the three-ETF one-minute lane would reuse the same short
   market regime and increase multiple-testing pressure.
2. Expanding the one-minute universe to 63 symbols would add cross-sectional
   trades but not materially increase chronological evidence.

The five-minute lane sacrifices fill precision in exchange for much stronger
time coverage. Its historical execution assumptions therefore remain more
conservative than the live one-minute paper executor.

## Data Contract

Import only `price_intraday_vol_5min.csv` from the existing immutable source
archive into a new content-addressed snapshot.

Required source identity:

- archive SHA-256: the verified source archive hash;
- member SHA-256: the verified five-minute member hash;
- provider/feed: `tiingo/iex`;
- bar size: `5min`;
- allowed symbols: exactly ordered `AAPL`, `QQQ`;
- regular XNYS sessions only;
- timestamps normalized from the declared source timezone to UTC;
- no forward fill across missing bars or sessions.

Quality acceptance requires valid OHLC relations, positive prices, unique
symbol/timestamp rows, calendar-valid sessions, expected five-minute grid
coverage, and quantified missing-bar evidence. Sessions failing a production
symbol quality check are excluded for both symbols so every phase uses the
same calendar.

The new snapshot, derived bars, manifest, quality evidence, and DuckDB views
remain separate from the current one-minute snapshot.

## Chronological Isolation

Use a named `60/20/20` split policy for this long-history lane:

- discovery train: first 60%;
- validation: next 20%;
- campaign final: last 20%.

The combined validation and final interval must contain at least 90 sessions,
and the final interval alone must contain at least 60 sessions. If data
quality exclusions make either requirement false, the campaign fails closed.

The final interval is a campaign-wide one-use capability, not a per-proposal
capability. Multiple hypotheses may use train and validation, but only one
sealed survivor neighborhood may consume the final interval. After that
consumption, new tuning must use newly accrued forward data or start a new
dataset generation whose final dates do not overlap the consumed campaign
final.

This prevents repeated proposals from adapting to the same nominal holdout.

## Strategy and Execution Contract

Extend the closed DSL with `signal_bar_size = "5min"`. The new lane permits
only bounded, data-only conditions using causal features available at a
completed five-minute bar.

Initial hypothesis families are deliberately diverse:

1. trend pullback continuation;
2. opening-range breakout and reclaim;
3. VWAP dislocation mean reversion under a non-bearish regime;
4. multi-bar momentum continuation with volatility and time-of-day controls.

AI may propose hypotheses and bounded variants, but it cannot emit code,
change gates, select arbitrary symbols, or access final data.

Historical entries fill at the next five-minute bar open. Historical exits
use the first subsequent five-minute boundary satisfying the compiled rule.
If a stop and target are both reachable inside one bar and their order is
unknown, the engine applies the adverse outcome first. Existing fees and
slippage scenarios remain, and the 1.5-times cost sensitivity remains a hard
requirement. No leverage or short exposure is permitted.

Live paper execution may consume one-minute Alpaca IEX bars, aggregate them
into closed five-minute signal bars, and submit only after bar completion.
Historical five-minute fills are not made artificially more precise to imitate
the live feed.

## Metrics and Gates

All existing hard gates remain unchanged. The long-history lane adds three
fail-closed gates evaluated only after the campaign final is consumed:

1. `INSUFFICIENT_OOS_SESSIONS`: validation plus final must contain at least 90
   accepted sessions.
2. `COST_ADJUSTED_ANNUALIZED_RETURN_TOO_LOW`: compound the chronological OOS
   session returns after the 1.5-times cost sensitivity and annualize with 252
   sessions; required value is at least 0.10.
3. `OOS_INFORMATION_RATIO_TOO_LOW`: annualized mean active return divided by
   sample tracking error, using QQQ close-to-close session return as the
   benchmark; required value is at least 0.5.

The report also shows non-annualized OOS return, QQQ return, excess return,
tracking error, Sharpe, MDD, profit factor, trade count, exposure, turnover,
cost paid, and P&L by symbol. IR is undefined with fewer than two active-return
observations or zero tracking error and must fail closed rather than be set to
an artificial value.

Annualized return and IR are never used to rank candidates that failed another
hard gate. Among complete survivors, ranking continues to prefer return
quality, cost resilience, drawdown, walk-forward consistency, and parameter
stability.

## Research Workflow

1. Verify and import the five-minute source member.
2. Build and accept its independent catalog.
3. Freeze the campaign split and final-use ledger before hypothesis search.
4. Generate hypotheses from train evidence only.
5. Expand bounded DSL neighborhoods and backtest train.
6. Preselect on train, then evaluate validation.
7. Require profitable parameter neighbors, rolling walk-forward consistency,
   start-date stability, symbol concentration, sample size, cost resilience,
   and null-test significance.
8. Seal one survivor neighborhood and consume the campaign final once.
9. Evaluate all old and new hard gates.
10. Register complete survivors as `paper_shadow`; preserve every rejection and
    its evidence.

No strategy is promoted merely because its annualized return crosses 10%.

## Failure Handling

- Data provenance, timezone, calendar, or coverage ambiguity rejects the
  snapshot.
- An already consumed campaign final cannot be reopened by resume, a new
  proposal ID, or a code-version change.
- Missing benchmark sessions reject IR evidence.
- Non-finite annualized metrics reject the candidate.
- Provider transitions remain separate datasets and require overlap analysis.
- Missing paper credentials do not alter research results; qualified strategies
  remain `paper_shadow` without simulated fills.

## Verification

Tests must cover:

- safe extraction and deterministic identity of only the approved archive
  member;
- source-timezone to UTC conversion and XNYS grid correctness;
- data-quality rejection and shared-session intersection;
- deterministic 60/20/20 allocation and minimum OOS lengths;
- campaign-wide final one-use enforcement across proposal IDs;
- five-minute causal feature timing and next-bar fills;
- adverse same-bar stop/target ordering;
- annualized 1.5-times-cost return calculations;
- QQQ benchmark alignment and IR calculations;
- all three new fail-closed gates;
- preservation of every existing gate and one-minute behavior;
- deterministic experiment replay, registry transitions, and Chinese reports;
- paper aggregation from closed one-minute bars to five-minute signals without
  early orders.

Completion requires the full test suite, static checks, an immutable formal
experiment, and evidence that at least one strategy passes all old and new
gates into `paper_shadow`.
