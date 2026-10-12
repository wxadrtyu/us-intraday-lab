# Full-market daily technical multifactor design

## Scope and evidence boundary

This campaign is a new full-market, long-horizon technical study. It may read
only the frozen Alpaca SIP daily `OHLCV/VWAP/trade_count` substrate and the
frozen point-in-time monthly eligibility table. News, announcements,
regulatory records, SEC forms, issuer events, fundamentals, and inferred issuer
attributes are forbidden. The prior 527-symbol daily studies and all SIP
five-minute, quote, and trade families remain frozen and may not be rescued,
renamed, or reused as fresh hypotheses.

The source audit fixed the daily substrate at 6,533,779 rows, 9,817 symbols and
881 sessions from 2020-07 through 2023-12. The 2021-2023 monthly eligible panel
contains 81,774 symbol-months and 3,270 symbols. Every date through 2026 is
consumed. Results are discovery evidence only and can at most preregister a new
prospective shadow observation beginning after the research cutoff; they are
never described as independent OOS evidence.

## Causal universe and clocks

- Membership is the frozen monthly point-in-time eligibility row applicable to
  the signal session. No present-day symbol list or later month may repair it.
- Features use only completed daily bars. A decision formed after session `t`
  may first enter at the open of session `t+1` for the standard and cost stress,
  and `t+2` for the required one-session-delay stress.
- A selected symbol missing an entry or exit price invalidates that portfolio
  cell. Missing bars are never cash, zero return, forward-filled, or deleted
  after observing performance.
- Portfolios are equal-weighted across selected names and overlapping cohorts.
  No leverage, volatility-target rescue, or issuer-specific override is
  permitted.

## Five frozen technical families

All cross-sectional inputs are winsorized and ranked within that session's
eligible universe using only available contemporaneous observations. Minimum
history is enforced before ranking.

1. `residual_momentum`: 252-session return excluding the most recent 21
   sessions, residualized each session against market return and 60-session
   realized volatility.
2. `trend_quality`: 126-session log-price slope divided by regression residual
   volatility, confirmed by the fraction of closes above the 63-session mean.
3. `low_vol_trend`: positive 126-session trend rank combined with inverse
   63-session realized-volatility rank; symbols with non-positive trend are
   ineligible.
4. `liquidity_confirmed_breakout`: distance from the prior 126-session high,
   confirmed by 20-session dollar-volume rank relative to its own 126-session
   median and by positive 20-session VWAP displacement.
5. `trend_conditioned_reversal`: negative five-session return rank, allowed
   only when the 126-session return is positive and the close remains above the
   126-session moving average.

These are economic families, not knobs. Direction, feature equations, and
minimum histories are immutable after any outcome is read.

## Frozen 400-cell grid

The grid is the Cartesian product of:

- five families above;
- four rebalance intervals: 5, 10, 20, and 21 sessions;
- four holding periods: 5, 10, 20, and 42 sessions; and
- five portfolio sizes: top 10, 20, 40, 80, and 120 symbols.

This yields exactly 400 cells. The deterministic tie break is normalized symbol
then source row identity. Standard cost is 9 bp round trip; required stress is
18 bp. Both cost scenarios and the delayed-entry scenario use identical signals,
membership, selections, and missingness decisions.

## Fail-closed gates

No threshold may be relaxed. A cell must clear the authoritative gate contract,
including development annualized return greater than 40%, MDD below 20%, IR at
least 1.0, z at least 3.0, four of five positive chronological folds, all frozen
start-date observations positive, at least 70% passing local-neighborhood share,
9/18 bp and delay stress, cumulative/global Bonferroni p at or below 0.05, and
both 500-repetition native maxT methods. Where an inherited historical or
consumed-period gate cannot be interpreted as independent evidence, it remains
a labeled diagnostic and cannot promote a candidate. A contract discrepancy
stops the run rather than selecting the favorable interpretation.

Because no independent OOS period remains, even a complete training survivor
is not production-qualified. The only permitted terminal action is to freeze an
unused prospective shadow protocol; Paper, broker, routing, and monitoring-pool
changes remain forbidden.

## Artifacts and atomicity

Each stage writes immutable source hashes, the exact policy hash, completed-cell
count, invalid-cell reasons, cumulative trial count, and an atomic checkpoint.
Tests must verify universe causality, feature lagging, grid cardinality,
missingness failure, cost/delay parity, and outcome blindness before the first
return read.
