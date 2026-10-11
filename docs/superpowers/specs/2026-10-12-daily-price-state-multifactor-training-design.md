# Daily price-state multi-factor training design

## Boundary

This is a new, frozen training-only hypothesis. It is not a rescue or inversion
of the rejected continuous trend ranks. It uses discrete states formed entirely
from the last completed daily OHLCV bar and its trailing history, mapped with a
strictly-earlier-date join to each execution session.

The universe remains the 527-symbol 2021-2023 coverage-limited sample, not the
full market. Development and consumed periods remain unopened. No strategy
version, Paper state, monitoring pool, broker route, or order path may change.

## Immutable inputs

- Daily source files: filenames dated 2020-07 through 2023-12 under the frozen
  Alpaca SIP daily directory.
- Daily source tree SHA-256:
  `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`.
- Execution cube SHA-256:
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- Training period: 2021-01-01 through 2023-12-31 only.

## Frozen primitives

All ratios fail closed when their denominator is nonpositive.

- `return_1 = close[t] / close[t-1] - 1`
- `return_5 = close[t] / close[t-5] - 1`
- `momentum_20 = close[t] / close[t-20] - 1`
- `close_location = (close[t] - low[t]) / (high[t] - low[t])`
- `body_location = (close[t] - open[t]) / (high[t] - low[t])`
- `true_range = max(high-low, abs(high-close[t-1]), abs(low-close[t-1]))`
- `range_ratio_20 = true_range / median(true_range, 20)`
- `compression_5_20 = median(true_range, 5) / median(true_range, 20)`
- `volume_ratio_20 = volume / median(volume, 20)`
- `prior_low_20 = min(low[t-20:t-1])`
- `failed_breakdown = low[t] < prior_low_20 and close[t] > prior_low_20`

## Frozen families and eligibility

Scores are equal-weight averages of within-session percentile ranks of the
listed oriented primitives. An ineligible row has no score and cannot trade.

1. `capitulation_recovery`: `return_1` at or below the session 20th percentile,
   `volume_ratio_20 >= 1.25`, and `close_location >= 0.55`; rank `-return_1`,
   `volume_ratio_20`, and `close_location` high first.
2. `downside_exhaustion`: `return_5` at or below the session 20th percentile,
   `range_ratio_20 >= 1.25`, and `close_location <= 0.35`; rank `-return_5`,
   `range_ratio_20`, and `-close_location` high first.
3. `compression_uptrend`: `compression_5_20 <= 0.70`, `momentum_20 > 0`, and
   `close_location >= 0.60`; rank `-compression_5_20`, `momentum_20`, and
   `close_location` high first.
4. `volume_accumulation`: `return_1 > 0`, `volume_ratio_20 >= 1.50`,
   `close_location >= 0.70`, and `body_location > 0`; rank `return_1`,
   `volume_ratio_20`, `close_location`, and `body_location` high first.
5. `failed_breakdown_recovery`: `failed_breakdown`, `body_location > 0`, and
   `close_location >= 0.60`; rank `-return_5`, `range_ratio_20`,
   `close_location`, and `body_location` high first.

## Frozen grid and economics

- Five families.
- Decision bars: 2, 5, 11, 17, 23.
- Holding bars: 1, 2, 4, 6.
- Top counts: 5, 10, 20, 40.
- Total: exactly 400 cells.
- Standard round-trip cost: 9 bp.
- Stress round-trip cost: 18 bp.
- Delay stress: one execution bar later at 9 bp.
- Deterministic ordering: score descending, symbol ascending.
- If fewer than K eligible names exist, trade all available names; zero eligible
  names is an explicit zero-signal session.

## Frozen retention gate

A cell passes only if it is valid, has at least 500 signal sessions, standard
annualized return at least 20%, information ratio at least 0.8, maximum
drawdown below 20%, at least two positive calendar years, positive 18 bp
annualized return, and positive delayed annualized return.

The family may recommend acquiring a separately frozen development dataset only
if all 400 cells complete, no cell is invalid, and at least two distinct
families retain a cell. Otherwise it is frozen rejected with no strategy
version created.
