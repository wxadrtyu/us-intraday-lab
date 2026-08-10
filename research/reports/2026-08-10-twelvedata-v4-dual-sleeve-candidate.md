# TwelveData v4 dual-sleeve development candidate

## Decision

Freeze v4 as a development candidate, but do not promote it to `paper_shadow`.
The 2026H1 interval was already consumed by v3 and must not be reused to select,
tune, or approve v4. Promotion therefore requires a genuinely new prospective
interval under the unchanged hard gates.

## Hypothesis

The strategy is long-only and has at most 100% gross exposure. It separates the
capital into two fixed 50% sleeves; unused sleeve capital remains cash.

1. The stock sleeve observes minute 45, selects at most the strongest eligible
   stock, enters at minute 46, takes profit at 2%, and otherwise exits near
   minute 330. Eligibility requires causal VWAP, relative-volume, opening-range,
   absolute-return, excess-return, and bounded-SPY conditions.
2. The market sleeve observes SPY at minute 30, enters at minute 31 only when
   the current RTH return is in a bounded positive range and the prior SPY RTH
   session was positive, then exits at a frozen afternoon minute.
3. Each active sleeve independently pays the 1.5x round-trip cost of 9 bps. The
   benchmark uses SPY over the exact exposure interval and sleeve weight.

The architecture is materially different from v3's mutually exclusive,
full-capital stock-or-fallback choice. Simultaneous half-sized sleeves reduce
single-trade and action-timing dependence without adding leverage.

## Rejected precursor

A 3,888-cell scan of equal-weight stocks with fixed exits plus a simultaneous
fixed-weight SPY sleeve had zero survivors. No cell reached the 8% training
annual-return floor. Its attractive 2024-2025 cells had only about 3.3% training
return and roughly 21% training drawdown, so this precursor was rejected as a
recent bull-regime fit.

The exact-take-profit stock family alone also remained insufficient. Six cells
passed combined research screens, but every survivor selected only one stock;
their training annual returns were about 5.8%-6.4%, below the 8% floor.

## Frozen development neighborhood

The focused v4 neighborhood contains 36 combinations:

- stock excess floor: 0.50% or 0.75%;
- stock opening-range position floor: 0.60, 0.65, or 0.70;
- SPY minute-30 return floor: 0.20% or 0.30%;
- SPY exit minute: 240, 300, or 330;
- fixed stock and SPY sleeve weights: 50% each.

All other conditions are fixed. After exact `[31, exit)` SPY interval correction,
23 of the 36 combinations passed the core development screen. The ranked
representative used a 0.75% stock excess floor, 0.70 opening-range floor, 0.30%
SPY floor, and minute-330 SPY exit.

## Development evidence

All returns include 9 bps per active sleeve. The representative produced:

| Segment | Annual return | Matched-SPY IR | MDD | PF |
|---|---:|---:|---:|---:|
| 2020-2023 train | 8.53% | -0.394 | 4.58% | 1.584 |
| 2024 | 15.93% | 1.535 | 2.78% | 2.140 |
| 2025 | 8.74% | -0.075 | 3.45% | 1.463 |
| 2024-2025 OOS | 12.30% | 0.682 | 3.45% | 1.744 |

The combined OOS interval had 182 sleeve trades, 31.61% maximum positive-symbol
concentration, and five positive time-fold annual returns: 12.36%, 18.37%,
7.42%, 21.31%, and 3.12%.

Start-date offsets of 0, 20, 40, and 60 sessions retained 11.11%-12.30%
annualized return, 0.553-0.695 IR, and 3.45% MDD. Removing the worst-return
symbol still left 20.92% cumulative OOS return; the worst leave-one-symbol-out
drawdown was 4.37%. The observed 25.64% OOS total return exceeded both 500-run
95th-percentile null thresholds: 14.20% for session-signal permutation and
12.90% for circular shift.

## Promotion boundary

These results justify implementation of one common exact-minute evaluator and
prospective observation, not broker orders. The frozen family must next pass:

- reproduction from the formal evaluator;
- all unchanged cost, return, IR, drawdown, profit-factor, trade-count,
  walk-forward, start-date, leave-one-symbol-out, concentration, parameter, and
  null gates;
- a new, predeclared forward interval that was not used by v1-v3 or this scan.

Until then, lifecycle state remains research-only and no Alpaca paper orders
may be emitted.
