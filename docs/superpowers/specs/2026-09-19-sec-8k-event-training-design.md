# SEC 8-K Structured-Event Training Design

## Objective and authorization

Test whether newly accepted, issuer-specific Form 8-K item categories provide a
distinct long-only intraday return source in the fixed 527-symbol 2021-2023
training sample. The sample is coverage-limited and is never described as full
market. The user has instructed the research loop to continue autonomously after
failed clues, so this line begins after freezing the rejected SEC 10-Q and Form 4
families without tuning either one.

This is a versionless training-feasibility screen. It cannot authorize
development-period ranking, Paper activation, pool mutation, or order routing.

## Alternatives and decision

Three genuinely distinct official sources were considered:

1. SEC structured 8-K item metadata: high issuer coverage, exact acceptance
   timestamps, and clear event categories without text-model hindsight.
2. SEC 13F holdings: broad but quarterly and substantially delayed, so it is a
   weaker match for short-horizon intraday selection.
3. SEC 8-K document text: potentially richer but introduces document retrieval,
   amendments, exhibits, language models, and a large taxonomy before the basic
   event mechanism is tested.

Use option 1. Do not retrieve filing documents or combine this line with news,
FINRA, Cboe, Federal Reserve, CFTC, SEC 10-Q, SEC Form 4, quote, or trade-print
features.

## Official immutable source

Use the SEC submissions API documented at
`https://www.sec.gov/search-filings/edgar-application-programming-interfaces`:

- current submission history:
  `https://data.sec.gov/submissions/CIK##########.json`;
- historical fragments listed by each current response under `filings.files`:
  `https://data.sec.gov/submissions/<exact-listed-name>`.

Reuse the 461 unique current-CIK raw responses already frozen by the SEC 10-Q
line, including their hashes. For every exact matched CIK, inspect the declared
`filingFrom` and `filingTo` ranges and acquire only listed historical fragments
that intersect 2021-01-01 through 2023-12-31. Requests are sequential, use a
declared user agent, bounded retries, and no more than four requests per second.
Freeze URL, retrieval time, byte count, and SHA-256. Never synthesize a fragment
name or infer omitted history.

Validate parallel-array lengths and require the documented fields
`accessionNumber`, `filingDate`, `reportDate`, `acceptanceDateTime`, `form`,
`items`, `size`, and `primaryDocument`. Preserve every missing, malformed,
duplicate, amended, or unmatched row with a reason. Raw JSON, manifests, and
caches stay outside Git.

## Fixed sample and identity

- The immutable event cube SHA-256 is
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- It contains exactly 527 symbols observed during 2021-2023.
- Reuse the frozen exact SEC identity snapshot: 462 matched symbols and 65
  unmatched symbols. Preserve the unmatched set unchanged.
- Join submissions by exact numeric issuer CIK. Shared CIKs may map to multiple
  exact sample share classes and remain explicit.
- The current CIK association is retrospective feasibility evidence, not a
  historical security master or independent out-of-sample evidence.

## Qualifying filing and causal availability

Only original `form == "8-K"` submissions with acceptance timestamps and filing
dates inside 2021-2023 can create signals. `8-K/A` rows remain audit evidence and
never create or revise a signal. Deduplicate only exact accession numbers; a
duplicate with conflicting metadata fails closed.

The normalized item set is the exact comma-delimited SEC `items` field after
whitespace trimming. Unknown or blank items remain explicit and do not receive a
category. No item is inferred from document text, primary-document name, or
description.

Although `acceptanceDateTime` is available, the frozen event cube lacks exact
decision timestamps. A filing therefore becomes usable only on the first sample
session strictly after its acceptance calendar date. This deliberately excludes
same-day signals, including pre-market filings. The state remains active for
that session and the next two sample sessions, then expires. Later amendments do
not rewrite earlier states.

## Frozen event categories and features

The five categories are exact SEC item membership:

1. earnings/results: item `2.02`;
2. material agreement: item `1.01`;
3. acquisition/disposition: item `2.01`;
4. director or officer change: item `5.02`;
5. other material event: item `8.01`.

A filing may belong to more than one category. For each issuer-session state,
aggregate only filings already causally available and expose:

- one binary indicator per category;
- exact active accessions and latest acceptance timestamp;
- active filing count and total declared item count;
- `log1p(size)` using the as-filed SEC byte-size metadata;
- days since the latest accepted filing.

No absent category or missing filing is converted into an economic zero. Raw
coverage inventory is computed before projection onto event rows and carried as
separate issuer counts and global training years.

## Frozen strategy families

Each decision clock jointly ranks all causally covered eligible sample symbols.
Ties break by symbol. Portfolios are equal-weight, long-only, gross exposure at
most one, and flat at the frozen exit. Zero-signal days are valid.

1. earnings/results plus positive open-to-decision continuation;
2. material agreement plus positive open-to-decision continuation;
3. acquisition/disposition plus positive open-to-decision continuation;
4. director/officer change plus open-to-decision reversal;
5. other material event plus positive open-to-decision continuation.

The category indicator multiplies the corresponding causal intraday return rank.
Filing size, item count, and recency are retained for audit and coverage but are
not additional tuned dimensions in the initial screen.

## Coverage gate

Before any return evaluation, require:

- every required current response and intersecting historical fragment to have
  an immutable valid source record;
- at least 300 exact-mapped issuers with at least three qualifying categorized
  original 8-K filings during training;
- at least 5,000 total qualifying categorized issuer-filing events;
- qualifying events in 2021, 2022, and 2023;
- no unexplained duplicate accession, parallel-array mismatch, or missing
  required historical fragment.

Count shared-CIK filings once per exact sample symbol because the strategy acts
on symbols, but publish both unique-CIK and symbol-event totals. If the gate
fails, freeze evidence and emit `ABANDON_SEC_8K_EVENT_COVERAGE_GATE` without
running the return grid.

## Frozen grid and retention gates

- Decision bars: `2, 5, 11, 17, 23`.
- Holding bars: `1, 2, 4, 6`.
- Top counts: `1, 3, 5, 10`.
- Total: exactly 400 cells.
- Costs: 9 bp standard, 18 bp stress, and one-bar delayed entry at 9 bp.

Retain a cell only with at least 120 signal sessions, standard annualized return
at least 20%, information ratio at least 0.8, maximum drawdown below 20%, at
least two positive calendar years, positive 18 bp annualized return, and positive
delayed annualized return. Continue to development acquisition only if retained
cells span at least two event categories. Otherwise emit
`ABANDON_SEC_8K_EVENT_NO_VERSION_CREATED`.

## Failure handling and verification

Transport, schema, duplicate, timestamp, and historical-fragment failures are
preserved and fail closed. Interrupted downloads never replace accepted bytes.
Every feature row preserves event keys and an explicit coverage reason.

Tests cover current and historical response schemas, declared-fragment selection,
immutable resume, exact CIK and shared-CIK identity, item parsing, amendments,
duplicates, next-session availability, three-session expiry, raw coverage
inventory, 400-cell cardinality, training boundary, cost/delay gates, and all
no-execution invariants.

No development or consumed period is loaded. No strategy version, broker,
submit/cancel call, Paper activation, pool mutation, order route, or shutdown is
allowed. A training pass authorizes only a separately reviewed development-data
acquisition proposal.
