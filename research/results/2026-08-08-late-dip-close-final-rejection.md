# Late Dip Close 5m - Final Blind-Test Rejection

## Decision

`late-dip-close-5m-v1-c6bc69016ace` is rejected and must not enter the paper-trading pool.
The one-use campaign final was consumed once and will not be reopened for parameter selection.

## Data and split

- Dataset: `tiingo-iex-5min-d26da6464f777dffe6abc0a85fcbba00`
- Accepted complete sessions: 315
- Train: 189 sessions, 2025-01-02 through 2025-11-25
- Validation: 63 sessions, 2025-11-26 through 2026-03-13
- Final blind test: 63 sessions, 2026-03-16 through 2026-07-02
- Selection SHA-256: `125ab94e00d8d26394ca2b73c625d74642a7106efdda474e0f77cbd8d04aba9f`

## Pre-final evidence

- Train 1.5x-cost annualized return: 10.27%
- Train maximum drawdown: 7.86%
- Train profit factor: 1.59
- Validation 1.5x-cost annualized return: 12.31%
- Validation maximum drawdown: 1.04%
- Validation profit factor: 3.44
- Closed trades before final: 114
- Profitable validation windows: 4 of 5
- Validation IR versus QQQ: 1.69
- Validation symbol profit share: AAPL 30.08%, QQQ 69.92%
- Null test: passed both 200-repetition methods; observed profit 13,167.36 versus 95th-percentile thresholds 7,218.36 and 5,951.63
- Null evidence SHA-256: `30f4115ecb8210fe1535f6565698ebc4a070605b9ba83ecaf08fece30cb63df7`

## Final evidence

- Final closed trades: 22
- Final base profit factor: 0.43
- Final base maximum drawdown: 3.88%
- Final symbol P&L: AAPL -3,545.60; QQQ +566.28
- Combined validation plus final OOS sessions: 126
- Combined OOS 1.5x-cost annualized return: -0.87%
- Combined OOS total return at 1.5x costs: -0.43%
- Combined OOS base total return: 0.18%
- QQQ benchmark total return: 16.02%
- OOS information ratio: -1.43

## Interpretation and next step

The pre-final edge did not survive the regime change in the sealed interval. The next campaign
must not optimize against this consumed final. Research may use the failure diagnostically, but
promotion requires a new independent holdout from previously unused symbols or genuinely new
forward sessions. The preferred next data scope is SPY/IWM five-minute history plus future Alpaca
paper observations, with the same cost, drawdown, trade-count, diversification, null, OOS-return,
and IR gates retained.
