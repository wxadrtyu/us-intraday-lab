# Daily risk-budget multi-factor training design

## Decision and alternatives

News, filings, regulatory notices, and every other issuer-event source are out
of scope permanently. Three technical-only alternatives were considered:

1. a causal long-only risk-budgeted cross-sectional portfolio;
2. a dollar-neutral long/short portfolio; and
3. a single-index timing overlay.

The first is frozen for this experiment. It preserves direct equity exposure,
does not assume borrow availability or shorting costs, and tests whether
portfolio construction rather than another raw signal variant can control the
drawdown observed in the rejected daily swing study. The prior 2021-2023
results are consumed training evidence, so a passing result can only authorize
acquisition of separate development data; it cannot establish out-of-sample
performance or production readiness.

## Frozen inputs and causal eligibility

Only completed daily OHLCV bars from the frozen 527-symbol coverage-limited
sample are permitted. It is not a full-market sample. Inputs remain fixed at
daily source SHA-256
`0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`
and symbol-container SHA-256
`399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.

A symbol is eligible on a feature date only when its completed close is at
least USD 5, trailing 20-session median close-times-volume is at least USD 5
million, and all inputs required by its family and 20-session realized
volatility are finite. Eligibility never inspects a future bar. A selected
symbol lacking the current or next required open invalidates the cell; missing
returns are never cash, zero, forward-filled, or silently removed.

## Five signal families

Each family is an equal-weight mean of same-date cross-sectional percentile
ranks with the stated orientation:

1. `diversified_quality`: positive 20/5 and 60/5 momentum, trend efficiency,
   distance to the prior 20-session high, and negative downside volatility.
2. `defensive_momentum`: positive 60/5 and residual 60/5 momentum, negative
   realized and downside volatility, and drawdown closest to zero.
3. `liquid_breakout`: positive distance to the prior 20-session high, 20/5
   momentum, five-to-20-session volume ratio, trend efficiency, and trailing
   dollar-volume percentile.
4. `stable_reversal`: negative one- and five-session returns, negative
   realized and downside volatility, and drawdown closest to zero.
5. `trend_reversal_blend`: positive 60/5 momentum and trend efficiency,
   negative one-session return, negative realized volatility, and drawdown
   closest to zero.

These families are frozen together before reading another outcome. No family
may be added or deleted after the run begins.

## Risk budget, execution, and exact grid

- Signal lags: 1, 2, 3, and 5 global trading sessions.
- Cohort lives: 1, 2, 5, and 10 sessions.
- Top counts: 10, 20, 40, 80, and 120.
- Five families produce exactly 400 cells.
- Within a cohort, eligible selected names receive inverse trailing 20-session
  realized-volatility weights. Each name is capped at 10% of total portfolio
  capital; unallocated capital remains cash.
- Portfolio gross exposure is multiplied by `min(1, 0.15 / market_vol_20)`,
  floored at 25%, where `market_vol_20` is the annualized volatility of the
  equal-weight return of all symbols with valid consecutive closes. It is
  shifted one completed session before use.
- The target portfolio is the arithmetic mean of active cohorts. Return is
  open-to-next-open. Turnover is one-half the absolute change across stock and
  cash weights.
- Standard cost is 9 bp times turnover; stress cost is 18 bp. Delay stress
  adds one global session to the signal lag at 9 bp. Ties break by symbol.

## Gates and side effects

A cell is retained only with at least 500 signal sessions, annualized return at
least 20%, information ratio at least 0.8, maximum drawdown below 20%, at least
two positive calendar years, positive 18 bp annualized return, and positive
one-session-delay annualized return. All 400 cells must be valid and at least
two families must retain a cell before separate development data may be
recommended.

No strategy version, development/consumed-period read, Paper state, monitoring
pool, broker route, or order operation is permitted. A failed gate freezes a
rejection and the research continues to a genuinely different technical-only
hypothesis.
