# SEC Fundamental Filing Training Design

## Objective

Test whether newly filed, issuer-specific accounting changes provide a distinct
long-only intraday return source inside the fixed 527-symbol research sample.
This is a versionless 2021-2023 training feasibility screen. It is not described
as full-market research and cannot authorize Paper or order routing.

## Alternatives and decision

Three sources were considered:

1. Filing timing and form intensity alone is highly causal but economically weak.
2. SEC XBRL accounting changes linked to exact filing accessions are issuer
   specific and have a direct post-filing-drift mechanism.
3. Splits and dividends are causal but too sparse and overlap adjusted-price
   handling already present in the event cube.

Use option 2. Do not combine it with news labels, CFTC state, Federal Reserve
state, Cboe volatility state, FINRA short volume, quotes, or trade prints.

## Fixed sample and identity contract

- The actionable research sample is exactly the 527 distinct symbols present in
  the frozen 2021-2023 event cube with SHA-256
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- The sample is explicitly coverage-limited and is never called full market.
- Freeze the official SEC `company_tickers_exchange.json` response and map only
  exact, case-sensitive ticker matches to CIKs.
- The initial read-only audit found 462 exact matches and 65 unmatched symbols.
  Unmatched symbols remain `SEC_IDENTITY_UNAVAILABLE`; ETF or historical-ticker
  identities must not be guessed, aliased, silently dropped, or provider-spliced.
- Current SEC ticker associations and current Company Facts are retrospective
  snapshots, not a historical security master. Any retained result remains
  feasibility evidence and is not independent OOS evidence.

## Official acquisition contract

- Sources are the SEC EDGAR submissions API and Company Facts API documented at
  `https://www.sec.gov/search-filings/edgar-application-programming-interfaces`.
- Request only the 462 exact-matched CIKs. Use a declared user agent, sequential
  requests no faster than four per second, bounded retries, and immutable raw
  JSON files outside Git.
- Freeze URL, retrieval timestamp, byte length, and SHA-256 for the ticker map,
  every submissions response, and every Company Facts response.
- Retain only original `10-Q` filings with filing dates from 2021-01-01 through
  2023-12-31. Amendments are evidence but do not create a new signal.
- Join Company Facts to submissions by exact accession number. Never infer a
  filing from a period end alone.

## Causal availability

- A filing becomes usable on the first event-cube session strictly after its SEC
  filing date. This deliberately ignores same-day availability even when the
  filing was accepted before the open.
- A filing state is active for that session and the next four event-cube sessions,
  then expires. There is no indefinite forward fill.
- Later filings never revise an earlier event in place. Duplicate accession,
  symbol-session, or issuer-period keys fail closed.

## Canonical accounting features

Use USD facts attached to the exact `10-Q` accession. Duration facts must end on
the filing report date and span 70-110 days. Instant facts must share that end
date. Apply the following frozen tag priorities, taking the first valid tag only:

- revenue: `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`,
  then `SalesRevenueNet`;
- gross profit: `GrossProfit`;
- operating income: `OperatingIncomeLoss`;
- cash: `CashAndCashEquivalentsAtCarryingValue`;
- assets: `Assets`;
- liabilities: `Liabilities`.

For every issuer, compare duration metrics with the nearest prior filing whose
period end is 330-400 days earlier, and instant ratios with the nearest prior
filing whose period end is 70-110 days earlier. Require finite positive revenue
and assets. Preserve each missing prerequisite with a reason code.

The five frozen features are:

1. `revenue_growth_acceleration`: current year-over-year revenue growth minus
   the preceding report's year-over-year growth;
2. `gross_margin_expansion`: current gross margin minus prior-year gross margin;
3. `operating_margin_expansion`: current operating margin minus prior-year
   operating margin;
4. `cash_asset_improvement`: current cash/assets minus prior-quarter cash/assets;
5. `deleveraging`: prior-quarter liabilities/assets minus current
   liabilities/assets.

Winsorize each feature cross-sectionally at the 1st and 99th percentiles, then
convert it to a cross-sectional percentile. No unavailable value may be imputed.

## Frozen strategy families

Each active session and decision clock ranks all sample symbols with a finite
issuer feature and causal open-to-decision return. Positive accounting changes
are required; zero-signal sessions are valid.

1. revenue acceleration plus intraday winner continuation;
2. gross-margin expansion plus intraday winner continuation;
3. operating-margin expansion plus intraday winner continuation;
4. cash/asset improvement plus intraday winner continuation;
5. deleveraging plus intraday winner continuation.

The accounting percentile multiplies the causal intraday-return percentile.
Ties break by symbol. The selected portfolio is equal-weight, long-only, has
gross exposure at most one, and is flat by the frozen exit.

## Grid and gates

- Decision bars: `2, 5, 11, 17, 23`.
- Holding bars: `1, 2, 4, 6`.
- Top counts: `1, 3, 5, 10`.
- Total: exactly 400 cells.
- Accounting: 9 bp standard, 18 bp stress, and one-bar delayed entry at 9 bp.
- Retain only cells with at least 120 signal sessions, annualized return at least
  20%, IR at least 0.8, max drawdown below 20%, at least two positive calendar
  years, positive 18 bp annualized return, and positive delayed annualized return.
- Continue to development acquisition only if retained cells span at least two
  accounting families. Otherwise emit
  `ABANDON_SEC_FUNDAMENTAL_FILINGS_NO_VERSION_CREATED` and stop this clue.

## Acquisition gate and terminal behavior

Before return evaluation, require at least 300 exact-mapped issuers with at least
four valid feature-bearing `10-Q` events during training, at least 1,200 total
feature-bearing filing events, and complete immutable source manifests. If this
gate fails, freeze the coverage evidence and abandon without evaluating returns.

No development or consumed period may be loaded during this screen. No strategy
version, broker module, pool mutation, Paper activation, submit/cancel call, or
order route is allowed. A training pass authorizes only a separately reviewed
development-data acquisition proposal.
