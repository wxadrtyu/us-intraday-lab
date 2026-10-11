# Daily Technical Multi-Factor Training Design

Date: 2026-10-12

## Goal and scope

Test one bounded, preregistered technical-indicator family using only the frozen
2021-2023 training period. The universe is the 527-symbol coverage-limited sample
in the frozen execution cube, not the full market. Passing training may recommend
a separately authorized development-data acquisition; it cannot create a
strategy version or activate Paper.

This design replaces the abandoned news and regulatory-event route. It is also
distinct from the exhausted same-session path-factor searches: every signal is
computed from a completed daily bar strictly before the execution session.

## Immutable inputs

- Daily SIP source root: `alpaca_sip_1day_v2`
- Daily source filenames: only monthly batches from 2020-07 through 2023-12
- Daily source tree SHA-256:
  `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`
- Execution cube SHA-256:
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`
- Training dates: 2021-01-01 through 2023-12-31
- Warm-up bars may begin 2020-07-01, but no warm-up outcome contributes to
  reported performance.
- Development, consumed, and blind-period files are forbidden.
- Files after 2023-12 are excluded before hashing and cannot be opened by the
  diagnostic.

## Point-in-time feature contract

For execution session `d`, use the most recent daily bar with date strictly less
than `d`. A symbol needs at least 60 completed daily observations. Missing bars
are not forward-filled. All rolling functions operate within symbol and use only
the completed history.

Let `lr` be the one-day close-to-close log return. Let `market_lr` be that date's
cross-sectional median `lr` among the frozen sample, and `residual_lr = lr -
market_lr`. The primitive factors are:

- `momentum_20_5 = log(close[t-5] / close[t-20])`
- `momentum_60_5 = log(close[t-5] / close[t-60])`
- `residual_momentum_60_5 = sum(residual_lr[t-59:t-5])`
- `reversal_5 = -log(close[t] / close[t-5])`
- `trend_efficiency_20 = abs(log(close[t] / close[t-20])) /
  sum(abs(lr[t-19:t]))`
- `realized_volatility_20 = std(lr[t-19:t]) * sqrt(252)`
- `downside_volatility_20 = sqrt(mean(min(lr[t-19:t], 0)^2)) * sqrt(252)`
- `drawdown_60 = close[t] / max(close[t-59:t]) - 1`
- `volume_confirmation = sign(momentum_20_5) *
  log(mean(volume[t-4:t]) / mean(volume[t-19:t]))`

On each execution session, convert every available primitive to a percentile
rank. Higher is better after explicitly negating volatility factors.

## Frozen signal families

Each family score is the arithmetic mean of its oriented percentile ranks:

1. `balanced_trend`: `momentum_20_5`, `momentum_60_5`,
   `trend_efficiency_20`, negative `downside_volatility_20`.
2. `residual_trend`: `residual_momentum_60_5`, `momentum_20_5`,
   `trend_efficiency_20`, negative `realized_volatility_20`.
3. `quiet_pullback`: `momentum_60_5`, `reversal_5`, `drawdown_60`, negative
   `downside_volatility_20`.
4. `volume_confirmed_trend`: `momentum_20_5`, `momentum_60_5`,
   `volume_confirmation`, `trend_efficiency_20`, negative
   `realized_volatility_20`.
5. `defensive_momentum`: `momentum_60_5`, `residual_momentum_60_5`,
   `drawdown_60`, negative `downside_volatility_20`, negative
   `realized_volatility_20`.

Ties break by symbol ascending. No learned weights, IC fitting, adaptive signs,
or post-result factor substitution is allowed.

## Frozen execution grid

Evaluate exactly 400 cells:

- five signal families;
- decision bars `(2, 5, 11, 17, 23)`;
- holding bars `(1, 2, 4, 6)`;
- top counts `(5, 10, 20, 40)`.

At a decision bar, hold an equal-weight long portfolio of the highest-scoring
available symbols. Standard execution enters at `p1_open`; the one-bar delay
enters at `p2_open`. Exit columns follow the existing execution-cube mapping for
the four holding periods. Charge 9 bp per completed trade in standard and delay
runs and 18 bp in the cost stress. Invalid or non-positive entry/exit prices make
the cell invalid; they are never converted to cash selectively.

## Frozen retention gate

A cell is retained only if all conditions hold:

- valid execution data;
- at least 500 signal sessions;
- standard annualized return at least 20%;
- standard information ratio at least 0.80;
- standard maximum drawdown below 20%;
- positive return in at least two of 2021, 2022, and 2023;
- 18 bp annualized return above zero;
- one-bar-delay annualized return above zero.

Training recommends acquiring separately frozen development data only when all
400 cells complete with zero invalid cells and at least two distinct signal
families retain a cell. Otherwise the family is frozen as rejected. No
development or consumed-period ranking, strategy version creation, Paper
activation, broker action, monitoring-pool mutation, or order routing is allowed.

## Verification

Unit tests must prove strict lagging, rolling-window definitions, deterministic
ranking, 400-cell cardinality, cost/delay behavior, missingness preservation, and
the two-family decision gate. The production runner must re-hash both immutable
inputs before reading OHLCV or execution outcomes and write immutable JSON,
Markdown, and parquet result artifacts.
