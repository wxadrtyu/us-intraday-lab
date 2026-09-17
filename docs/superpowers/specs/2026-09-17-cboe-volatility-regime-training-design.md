# Cboe volatility-regime training feasibility design

## Objective

Test a genuinely new causal source: prior-session option-implied volatility states from official Cboe index histories. This is a versionless 2021-2023 training feasibility screen, not an extension of exhausted OHLCV, quote, trade-print, news, or FINRA-flow families.

## Source and causal contract

- Official source: Cboe daily history CSVs for `VIX`, `VIX9D`, `VVIX`, `OVX`, `GVZ`, and `VXEEM`.
- Persist only rows dated 2021-01-01 through 2023-12-31 in an immutable external snapshot with per-source URL and SHA-256 evidence.
- A close dated `t` is usable only for an equity session strictly after `t`; same-session values are forbidden.
- Missing index dates and missing joins remain null. No forward fill across more than one equity session, provider splice, or retrospective substitution is allowed.
- Current source files can contain later dates, but later rows must be discarded before persistence and must never enter ranking, diagnostics, or reports.
- The Cboe CSVs are current retrospective histories without historical-vintage proof. Any retained result is therefore feasibility evidence only and cannot be called independent OOS or promoted without a separate revision-risk review.

## Frozen features and families

Create lagged levels, one-day changes, 20-session z-scores, and ratios using only earlier Cboe dates. Join them to the frozen full-market event table by prior equity session.

Five preregistered families combine the exogenous prior-session regime with causal open-to-decision cross-sectional state:

1. `near_term_fear_inversion_reversal`: high `VIX9D / VIX` ranks intraday losers for rebound.
2. `vol_of_vol_stress_reversal`: high `VVIX` z-score ranks intraday losers for rebound.
3. `oil_volatility_shock_continuation`: rising `OVX / VIX` ranks intraday winners for continuation.
4. `gold_volatility_divergence_reversal`: rising `GVZ / VIX` ranks intraday losers for rebound.
5. `em_volatility_divergence_reversal`: rising `VXEEM / VIX` ranks intraday losers for rebound.

Every decision ranks all point-in-time eligible event symbols with non-null causal features. No fixed ETF action universe is permitted.

## Frozen grid and accounting

- Decision bars: `2, 5, 11, 17, 23`.
- Holding bars: `1, 2, 4, 6`.
- Top counts: `1, 3, 5, 10`.
- Total: `5 * 5 * 4 * 4 = 400` cells.
- Costs: standard 9 bp round trip, 18 bp stress, and one-bar delayed entry at 9 bp.
- Use the existing event-return accounting, session portfolios, calendar-year returns, annualized return, information ratio, and maximum drawdown conventions.

## Retention and stop rules

A cell is retained only if all conditions hold:

- at least 120 signal sessions;
- standard annualized return at least 20%;
- standard information ratio at least 0.8;
- standard maximum drawdown below 20%;
- at least two positive calendar years;
- positive annualized return at 18 bp;
- positive annualized return after one-bar delay.

Acquire or inspect development data only if retained cells span at least two families. Otherwise record `ABANDON_CBOE_VOLATILITY_REGIME_NO_VERSION_CREATED`, create no strategy version, and move to another independent source.

## Safety boundary

This work must not import broker modules, activate Paper, change any existing pool, submit/cancel orders, or enable an order route. `paper_activation=false` and `order_route=FORBIDDEN` are mandatory in reports.
