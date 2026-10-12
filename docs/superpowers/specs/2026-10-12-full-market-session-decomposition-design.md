# Full-market daily session-decomposition design

## Decision and alternatives

The rejected close-based long-horizon family is frozen at zero retained cells.
This campaign tests a genuinely different technical return source: whether the
overnight close-to-open component and the regular-session open-to-close
component contain different, persistent cross-sectional information.

Three technical-only alternatives were considered. A market-breadth regime
overlay was rejected because breadth/regime routing has already been heavily
consumed. A volatility-risk-budget reconstruction was rejected because it
would primarily repair portfolio construction around previously failed
signals. Session decomposition is selected because it changes both the
economic signal and the realized exposure window while using only frozen daily
price, volume, VWAP, and trade-count data.

The user's standing instruction to continue autonomously supplies approval for
this preregistered design; no interactive A/B/C choice is required.

## Evidence boundary

Only the frozen Alpaca SIP daily substrate and frozen point-in-time monthly
universe may be read. Their identities remain:

- daily source SHA-256 `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`;
- monthly universe SHA-256 `3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81`.

News, announcements, regulatory records, SEC forms, issuer events,
fundamentals, classifications, and inferred issuer attributes are forbidden.
All dates through 2026 are consumed. A complete survivor could only define a
new prospective shadow protocol and cannot be described as independent OOS or
activated in Paper.

## Causal features and five families

For completed session `t`, define overnight log return as
`log(open_t / close_t-1)` and regular-session log return as
`log(close_t / open_t)`. Features use only data available by the close of `t`.
Every family ranks all point-in-time eligible symbols with finite required
history; exact ties break by normalized symbol. No price, liquidity, or
continuity filter may use a future bar.

1. `persistent_overnight_drift`: positive trailing overnight return and
   overnight hit rate, penalized by overnight volatility.
2. `overnight_underreaction`: positive trailing overnight return combined with
   negative trailing regular-session return and positive trailing dollar-volume
   rank.
3. `persistent_intraday_drift`: positive trailing regular-session return and
   intraday hit rate, penalized by intraday volatility.
4. `gap_reversal_quality`: negative most-recent overnight gap combined with
   positive trailing regular-session return and low overnight volatility.
5. `session_divergence`: positive trailing overnight return minus trailing
   regular-session return, confirmed by positive close-to-VWAP displacement
   frequency and dollar-volume rank.

Trailing statistics use one of four frozen lookbacks: 20, 42, 63, or 126
sessions. Each family/lookback equation is fixed before returns are evaluated.

## Exposure clocks and 400-cell grid

The economic family fixes the exposure window:

- `persistent_overnight_drift`, `overnight_underreaction`, and
  `session_divergence` hold only close-to-next-open exposure;
- `persistent_intraday_drift` and `gap_reversal_quality` hold only
  next-open-to-next-close exposure.

The standard decision after close `t` first trades the applicable leg of
session `t+1`; the delay stress first trades `t+2`. Active selections are
refreshed every 1, 5, 10, or 21 sessions and remain active for 1, 5, 10, or 21
sessions. The portfolio uses top 10, 20, 40, or 80 names. To keep multiplicity
fixed at exactly 400 cells, the grid is five families by four lookbacks by five
predeclared `(refresh, life)` pairs by four top counts. The pairs are
`(1,1)`, `(5,5)`, `(5,10)`, `(10,10)`, and `(21,21)`.

Selections are equal weighted and overlapping active cohorts are averaged.
Round-trip costs are 9 bp and 18 bp per completed one-session exposure leg.
The standard, cost, and delayed scenarios share signal values, selections, and
missingness decisions.

## Missingness and fail-closed rules

A selected symbol with a missing/nonpositive required entry or exit price, or
with zero volume and zero trade count on its exposure session, invalidates that
cell. It is never cash, zero return, forward-filled, or deleted. Insufficient
feature history produces a nonfinite score before selection and is never
imputed. Source triple-zero liquidity rows may be represented as explicit
missing technical inputs, but may not become valid realized exposure rows.

## Unchanged gates and artifacts

All prior hard gates remain unchanged: annualized return strictly above 40%,
maximum drawdown below 20%, IR at least 1, z-score at least 3, at least four of
five positive chronological folds, 9/18 bp and one-session-delay passage,
positive frozen start-date observations, at least 70% local-neighborhood
passage, global Bonferroni at most 0.05, and both 500-repetition native maxT
methods. Later gates run only for cells that pass every earlier gate.

The runner writes per-cell atomic JSON, a hash-chained checkpoint bound to the
source, universe, design, code, and gate identities, and tracked aggregate
results only after all 400 cells complete. Paper activation, broker access,
order routing, and monitoring-pool changes remain forbidden.

