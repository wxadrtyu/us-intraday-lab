# Daily-signal intraday multi-factor design

## Objective

Test a technical-only return source that is distinct from rejected overnight
and multi-session portfolios: rank stocks using completed daily bars, observe
the current open and its gap to the prior close, enter at that open, and exit at
the same session close. No news, issuer event, fundamental field, next-session
price, short sale, leverage, or overnight position is allowed.

The frozen inputs and 527-symbol coverage-limited 2021-2023 training scope are
unchanged. This is not a full-market or out-of-sample claim. Prior training
results are consumed; a pass can only recommend separate development data.

## Families and exact grid

The five preregistered cross-sectional percentile composites are
`diversified_quality`, `defensive_momentum`, `liquid_breakout`,
`stable_reversal`, and `trend_reversal_blend`, with the exact technical
definitions frozen in the daily risk-budget design.

- Signal lags: 1, 2, 3, and 5 global sessions.
- Top counts: 5, 10, 20, 40, and 80.
- Open-gap modes, all known at entry: `all`, `pullback` (gap at most zero),
  `quiet` (absolute gap at most 1.5%), and `followthrough` (gap above zero).
- Five families times four lags times five top counts times four gap modes give
  exactly 400 cells.
- Eligibility on the signal date requires close at least USD 5, trailing
  20-session median dollar volume at least USD 5 million, and finite factor
  inputs. The trade date additionally requires a positive finite open, prior
  close, and close. Ties break by symbol.
- Each active session holds the selected names equally from open to close and
  is flat afterward. Standard round-trip cost is 9 bp times gross exposure;
  stress cost is 18 bp. Delay stress adds one global signal session at 9 bp.
- A selected name missing its exit close invalidates the cell. Missing returns
  are never removed, filled, or treated as cash.

## Gates and side effects

Retention requires at least 500 active sessions, annualized return at least
20%, information ratio at least 0.8, maximum drawdown below 20%, at least two
positive years, positive 18 bp annualized return, and positive delayed return.
All 400 cells must be valid and at least two families must retain a cell before
separate development acquisition may be recommended.

No strategy version, development/consumed data, Paper state, monitoring pool,
broker route, or order operation may be created or changed.
