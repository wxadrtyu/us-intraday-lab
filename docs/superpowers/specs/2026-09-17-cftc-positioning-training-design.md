# CFTC positioning training feasibility design

## Objective

Test whether lagged institutional and leveraged-fund positioning in major U.S. financial futures supplies a genuinely different return source for the full-market intraday equity universe. This is a versionless 2021-2023 training screen. It does not extend the exhausted OHLCV, quote, trade-print, news, FINRA short-volume, Cboe volatility-regime, or Federal Reserve macro-regime families.

## Official data contract

- Source: CFTC Public Reporting Environment, TFF Futures Only dataset `gpe5-46if`.
- Request only report dates from 2021-01-01 through 2023-12-31 and only these exact contract-market codes:
  - `13874+`: S&P 500 Consolidated
  - `20974+`: NASDAQ-100 Consolidated
  - `239742`: Russell E-mini
  - `1170E1`: VIX Futures
  - `043602`: 10-Year U.S. Treasury Note
- Require exactly one row per contract and report date and 156 reports per contract. Preserve the response body hash, request URL, dataset identifier, selected columns, and every missing value.
- Persist only the selected training rows in an immutable external snapshot. Do not return, persist, rank, or report later dates.
- Current PRE data is retrospective and lacks historical-vintage hashes. Any retained result remains feasibility evidence and cannot be called independent OOS or promoted without a later revision-risk audit.

## Causal availability

CFTC says TFF reports normally publish Friday at 15:30 ET using positions from the preceding Tuesday. The API report date is not the release date, and CFTC states that holidays can change the schedule.

- Ordinary reports become usable at 00:00 ET on the Wednesday eight calendar days after the Tuesday report date. This is deliberately later than the normal Friday release and common holiday delays.
- The 2023 ION incident overrides ordinary availability with the official catch-up publication dates:
  - report 2023-01-31 -> published 2023-02-24
  - report 2023-02-07 -> published 2023-03-03
  - report 2023-02-14 -> published 2023-03-08
  - report 2023-02-21 -> published 2023-03-10
  - report 2023-02-28 -> published 2023-03-14
  - report 2023-03-07 -> published 2023-03-16
  - report 2023-03-14 -> published 2023-03-21
- A catch-up report is usable only from the next equity session after its publication date because publication occurred after the intraday decision clocks.
- Between releases, the last causally available positioning state remains the current weekly state. This is an explicit state contract, not missing-data forward fill. No report may be carried beyond 14 calendar days; longer gaps become unavailable.

## Frozen features and families

For each contract compute net positions divided by open interest for asset managers and leveraged money, one-report changes, and rolling 26-report z-scores. Every active session and decision clock still jointly ranks all point-in-time eligible equity symbols using their causal open-to-decision return.

1. `spx_asset_manager_confirmation`: positive S&P 500 asset-manager net-position z-score ranks intraday winners for continuation.
2. `nasdaq_leveraged_crowding_reversal`: positive NASDAQ-100 leveraged-money net-position z-score ranks intraday losers for crowding reversal.
3. `russell_institutional_divergence`: positive Russell asset-manager-minus-leveraged positioning z-score ranks intraday winners.
4. `vix_leveraged_stress_reversal`: positive VIX leveraged-money net-position change z-score ranks intraday losers for rebound.
5. `treasury_positioning_risk_confirmation`: positive 10-year Treasury asset-manager net-position change z-score ranks intraday winners.

## Frozen grid and gates

- Decision bars: `2, 5, 11, 17, 23`.
- Holding bars: `1, 2, 4, 6`.
- Top counts: `1, 3, 5, 10`.
- Total: exactly 400 cells.
- Accounting: 9 bp standard, 18 bp stress, and one-bar delayed entry at 9 bp.
- Retain a cell only with at least 120 signal sessions, annualized return at least 20%, IR at least 0.8, MDD below 20%, at least two positive calendar years, positive 18 bp annualized return, and positive delayed annualized return.
- Continue to development acquisition only if retained cells span at least two families. Otherwise record `ABANDON_CFTC_POSITIONING_NO_VERSION_CREATED`; the entire clue is then considered without sufficient training value and no local tuning is allowed.

## Safety and terminal conditions

No broker modules, Paper activation, pool mutation, strategy version, submit/cancel call, or order route is allowed. The line terminates only when at least two families pass the frozen training floor or all 400 cells complete with fewer than two retained families. A pass stops at a development-acquisition recommendation; it does not authorize acquisition, promotion, or execution in the same step.
