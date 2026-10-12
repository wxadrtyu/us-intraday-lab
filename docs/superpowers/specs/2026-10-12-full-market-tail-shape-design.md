# Full-market daily tail-shape multifactor design

## Decision and alternatives

The close-based trend family and the overnight/intraday session-decomposition
family are frozen at zero retained cells. This campaign tests a genuinely
different technical source: whether the shape of each stock's trailing daily
return distribution identifies persistent defensive or stable-compounding
cross-sectional premia.

Three alternatives were considered. Daily trade-size/price-impact proxies were
rejected because the SIP quote/trade and trade-participation families are
already exhausted and must not be renamed. Breadth/correlation routing was
rejected because breadth and regime families have been heavily consumed.
Return-distribution shape is selected because it uses a different economic
object from trend direction, gap decomposition, and intraday microstructure.
The user's standing autonomous-research instruction supplies design approval.

## Evidence and causal boundary

The only inputs are the frozen Alpaca SIP daily OHLCV/VWAP/trade-count substrate
and frozen point-in-time monthly universe, with identities:

- daily source SHA-256 `0d962e4c75d200df8837911db5f435c2049ffc6113248717b341e92154a98701`;
- universe SHA-256 `3dc89bc9ab09e193372b2071a3d5b84d04962d8f6cf1e679540a723959e51a81`.

News, announcements, regulation, SEC forms, issuer events, fundamentals, and
issuer classifications are forbidden. Features use completed bars through
session `t`; the standard portfolio first enters at the open of `t+1`, and the
delay stress enters at `t+2`. All 2021-2026 observations are consumed.

## Five frozen tail-shape families

For each lookback, calculate close-to-close log returns using only distinct
completed sessions. Cross-sectional percentiles are winsorized within the
point-in-time eligible universe and tied by normalized symbol.

1. `lottery_avoidance`: inverse rank of the maximum daily return, positive-tail
   mean, and return skewness.
2. `downside_resilience`: inverse rank of downside semideviation, worst daily
   return magnitude, and 5% expected shortfall magnitude.
3. `stable_compounding`: rank of arithmetic mean divided by downside
   semideviation, positive-session fraction, and inverse magnitude of the
   arithmetic-minus-geometric return drag.
4. `low_jump_intensity`: inverse rank of the fraction of returns whose absolute
   size exceeds two trailing standard deviations, inverse return kurtosis, and
   inverse overnight-gap variance share.
5. `tail_balance`: rank of upside 95% expected-tail mean divided by downside 5%
   expected-tail magnitude, inverse skewness magnitude, and inverse maximum
   peak-to-trough drawdown within the lookback.

Lookbacks are fixed at 20, 42, 63, and 126 sessions. Zero variance, too few
tail observations, or any nonfinite component leaves that family score missing;
no imputation or fallback equation is allowed.

## Portfolio grid and missingness

The exact 400 cells are five families by four lookbacks by five predeclared
`(rebalance, holding)` pairs by four top counts. Pairs are `(1,1)`, `(5,5)`,
`(5,10)`, `(10,10)`, and `(21,21)`; top counts are 10, 20, 40, and 80.
Selections are equal weighted and overlapping active cohorts are averaged.
Returns use the open after the decision through the open after the holding
horizon. Round-trip costs are 9 bp and 18 bp; the delay scenario uses 9 bp.

A selected symbol missing any required path bar, or having zero volume and zero
trade count on a held session, invalidates the entire cell. Missingness is never
cash, zero return, forward-filled, or deleted after performance is known.

## Gates and terminal actions

All hard gates remain unchanged: annualized return strictly above 40%, maximum
drawdown below 20%, IR at least 1, z at least 3, at least four of five positive
folds, 9/18 bp and one-session delay passage, positive frozen start-date
observations, at least 70% local-neighborhood passage, global Bonferroni at most
0.05, and both 500-repetition native maxT methods. Later gates run only after
all earlier gates pass.

Every cell is atomic and bound to source, universe, design, code, and gate
hashes. Even a complete consumed-period survivor can only define a new
prospective shadow protocol. Paper activation, broker access, order routing,
and monitoring-pool changes remain forbidden.
