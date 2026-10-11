# Daily swing multi-factor training design

## Objective and isolation

Test a multi-day long-only technical allocation model. This is distinct from
the rejected same-day intraday studies: signals are formed from completed daily
bars, entries occur at a later session open, and capital is carried through
overlapping multi-session cohorts. Only the frozen 527-symbol coverage-limited
2021-2023 training sample is used; it is not a full-market claim.

Inputs remain frozen at daily source tree SHA-256
`0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`
and symbol-container SHA-256
`399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
The daily files declare Alpaca SIP, split adjustment, and monthly as-of dates.

## Signal families

All primitives use completed closes and trailing history. Cross-sectional
scores are equal-weight percentile-rank composites.

1. `balanced_trend`: 20/5 and 60/5 momentum, trend efficiency, negative
   downside volatility.
2. `residual_trend`: 60/5 market-residual momentum, 20/5 momentum, trend
   efficiency, negative realized volatility.
3. `low_vol_momentum`: 60/5 and 20/5 momentum, negative realized volatility,
   negative downside volatility, drawdown closest to zero.
4. `short_reversal`: negative one-day and five-day returns, negative realized
   volatility, drawdown closest to zero.
5. `breakout_volume`: distance to the prior 20-session high, 20/5 momentum,
   five-to-20-session volume ratio, trend efficiency.

## Portfolio and exact grid

- Signal lags: 1, 2, 3, 5 global trading sessions after feature date.
- Cohort holding periods: 1, 2, 5, 10 sessions.
- Top counts: 5, 10, 20, 40, 80.
- Five families, for exactly 400 cells.
- Each session creates one equal-weight cohort. The target portfolio is the
  arithmetic mean of the most recent `holding` cohorts, so total exposure is at
  most 100% and overlapping capital is explicit.
- Portfolio return uses open-to-next-open returns with no forward-filled bars.
  A selected name without both required opens invalidates the cell.
- Turnover is one-half the absolute change across stock and cash weights.
- Standard cost is 9 bp times turnover; stress cost is 18 bp times turnover.
- Delay stress adds one global session to the frozen signal lag at 9 bp.
- Ranking tie break is symbol ascending.

## Retention and side effects

A cell passes only with at least 500 signal sessions, annualized return at least
20%, information ratio at least 0.8, maximum drawdown below 20%, at least two
positive years, positive 18 bp annualized return, and positive delayed return.
All 400 cells must complete with zero invalid cells and at least two families
must retain a cell before development acquisition may be recommended.

No development/consumed data, strategy version, Paper state, monitoring pool,
broker route, or order operation is permitted.
