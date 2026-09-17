# Federal Reserve macro-regime training feasibility design

## Objective and source contract

Test a versionless 2021-2023 training screen using a new exogenous source: daily Federal Reserve/FRED market-rate and broad-dollar series. The frozen series are `DGS2`, `DGS10`, `DGS30`, `DFII10`, `T10YIE`, and `DTWEXBGS`. FRED date filters must request only 2021-01-01 through 2023-12-31; later rows may not be returned, persisted, ranked, or reported.

Each source observation dated `t` is usable only for an equity session strictly after `t`. Join only the immediately prior equity session; do not carry values over a missing equity session, forward fill, splice providers, or replace missing data. Persist exact request URLs, response hashes, row counts, and an immutable external snapshot.

These are current retrospective series without historical-vintage proof. A retained result would be feasibility evidence only, not independent OOS evidence or a promotable strategy, until revision risk and exact publication timing receive a separate review.

## Preregistered families

All families use the external prior-session state only to activate a regime, then jointly rank every point-in-time eligible symbol at each decision clock by causal open-to-decision return:

1. `curve_inversion_stress_reversal`: unusually negative 10y-minus-2y slope ranks intraday losers for rebound.
2. `long_rate_shock_continuation`: positive one-day 10y yield shock ranks intraday winners.
3. `real_yield_shock_continuation`: positive one-day 10y real-yield shock ranks intraday winners.
4. `breakeven_inflation_shock_continuation`: positive one-day 10y breakeven shock ranks intraday winners.
5. `broad_dollar_shock_continuation`: positive one-day broad-dollar shock ranks intraday winners.

## Grid, gates, and stop rule

- Decision bars `2, 5, 11, 17, 23`; holdings `1, 2, 4, 6`; top counts `1, 3, 5, 10`.
- Exactly `5 * 5 * 4 * 4 = 400` cells.
- Standard 9 bp, 18 bp stress, and one-bar delayed 9 bp accounting.
- Retain only with at least 120 signal sessions, annualized return at least 20%, IR at least 0.8, MDD below 20%, at least two positive years, and positive 18 bp and delayed annualized returns.
- Development acquisition is recommended only when at least two families retain cells. Otherwise record `ABANDON_FED_MACRO_REGIME_NO_VERSION_CREATED` and move to another independent source without local tuning.

No broker import, Paper activation, pool mutation, strategy version, or order route is allowed.
