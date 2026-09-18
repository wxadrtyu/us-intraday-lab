# SEC Form 4 Insider-Flow Training Design

## Objective and authorization

Test whether newly disclosed open-market insider transactions provide a distinct
long-only intraday return source in the fixed 527-symbol, 2021-2023 training
sample. This sample is coverage-limited and is never described as full market.
The user's standing instruction is to continue autonomously after a falsified
clue, so this design proceeds without revisiting the exhausted SEC 10-Q family.

This is a versionless training-feasibility screen. It cannot authorize
development-period ranking, Paper activation, pool mutation, or order routing.

## Alternatives and decision

Three distinct sources were considered:

1. SEC Form 4 insider transactions: issuer-specific disclosed behavior, compact
   official bulk data, and a direct information/asymmetric-conviction mechanism.
2. SEC 8-K events: broader coverage but item and text parsing add a large,
   fragile taxonomy before the return hypothesis can be tested.
3. SEC Form 13F holdings: official and broad, but quarterly disclosure delay and
   manager-to-issuer aggregation make it materially lower frequency.

Use option 1. Do not combine it with news, FINRA short volume, Cboe volatility,
Federal Reserve state, CFTC positioning, SEC 10-Q accounting features, quote
paths, or trade-print paths.

## Authoritative source and immutable acquisition

Use only the SEC Insider Transactions Data Sets and official documentation:

- index: `https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets`;
- documentation: `https://www.sec.gov/files/insider_transactions_readme.pdf`;
- quarterly files:
  `https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/YYYYqQ_form345.zip`.

Acquire exactly the 12 ZIP files from 2021 Q1 through 2023 Q4, sequentially with
a declared user agent, bounded retries, and no more than four requests per
second. Freeze URL, response headers when available, byte count, retrieval time,
and SHA-256. Raw ZIPs and extracted tables remain outside Git. Interrupted or
invalid downloads never replace an accepted object.

Validate ZIP membership, UTF-8 tab-delimited parsing, documented keys, and
cross-table accession relationships. Preserve every malformed, duplicate,
unmatched, amended, late, or missing row with a reason; never repair provider
values silently.

## Fixed sample and identity contract

- The event cube is the immutable 2021-2023 cache with SHA-256
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- It contains exactly 527 sample symbols.
- Reuse the frozen exact SEC symbol-to-CIK identity snapshot from the prior
  training line: 462 matched symbols and 65 preserved unmatched symbols.
- Join ownership filings by exact numeric `ISSUERCIK`, not by a guessed ticker.
- Shared issuer CIKs may map to multiple exact sample share classes and must be
  retained explicitly.
- The current SEC identity association and retrospectively packaged quarterly
  files are feasibility evidence, not a historical security master or
  independent out-of-sample evidence.

## Qualifying transaction contract

Only original `DOCUMENT_TYPE == "4"` submissions can create a signal. Forms 3,
5, and all amendments remain audit evidence but do not create or revise a signal.

Join `SUBMISSION`, `REPORTINGOWNER`, and `NONDERIV_TRANS` by exact accession.
A qualifying transaction must have:

- `TRANS_CODE` equal to `P` or `S`;
- `P` paired with acquired code `A`, or `S` paired with disposed code `D`;
- finite positive `TRANS_SHARES` and `TRANS_PRICEPERSHARE`;
- a transaction date no later than the filing date;
- no equity-swap flag;
- a finite post-transaction holding when a holding-fraction feature is used.

Do not infer missing price, shares, owner role, transaction code, or direction.
Footnoted and indirect-ownership rows remain eligible only when the structured
fields above are complete; their footnotes and ownership type remain provenance.
Aggregate duplicate rows only after exact accession and transaction surrogate-key
validation. Dollar notional is shares times price and is never substituted with
current market price.

## Causal availability

The bulk tables contain a filing date but not an acceptance timestamp. A filing
therefore becomes usable only on the first event-cube session strictly after its
SEC filing date. Same-day use is forbidden. The filing state is active for that
session and the next four event-cube sessions, then expires.

Later amendments do not rewrite earlier states. When multiple original filings
for one issuer become active on the same session, aggregate only the filings
whose own availability precedes that session. Every output row carries source
accessions and the latest filing date used.

## Frozen filing features

For each original filing, aggregate qualifying transactions across exact owners:

- purchase notional from code `P`;
- sale notional from code `S`;
- net open-market notional divided by total absolute P/S notional;
- unique purchasing-owner count;
- officer/director purchase-notional share using structured owner relationships;
- purchased shares divided by post-transaction shares, only when the denominator
  is finite and positive;
- transaction-to-filing lag and late-report indicator.

Apply `log1p` to positive notionals, winsorize finite cross-sectional values at
the 1st and 99th percentiles per availability session, and convert them to
percentile ranks. Nulls remain null. A zero purchase is not imputed for a missing
or unmatched filing.

## Frozen strategy families

Every active decision clock jointly ranks all causally covered eligible sample
symbols. Ties break by symbol. Portfolios are equal-weight, long-only, gross
exposure at most one, and flat at the frozen exit. Zero-signal days are valid.

1. purchase-notional conviction plus intraday continuation;
2. purchase-to-post-holding conviction plus intraday continuation;
3. multi-owner purchase clustering plus intraday continuation;
4. officer/director purchase concentration plus intraday reversal;
5. positive net P/S balance plus intraday continuation.

Continuation multiplies the filing-feature percentile by the positive causal
open-to-decision return percentile. Reversal multiplies it by the percentile of
the negated open-to-decision return. Each family requires positive purchase
evidence; sales alone never create a long signal.

## Coverage gate

Before evaluating returns, require all of the following:

- all 12 quarterly ZIP files and manifests validate;
- at least 300 exact-mapped issuers each have at least three qualifying original
  Form 4 filings in 2021-2023;
- at least 3,000 total qualifying issuer-filing events;
- all three training years contain qualifying events;
- no unexplained duplicate accession or broken foreign-key relationship exists.

Coverage inventory is computed from the normalized filing table before its lossy
projection onto event rows. If the gate fails, freeze evidence and emit
`ABANDON_SEC_FORM4_INSIDER_FLOW_COVERAGE_GATE` without running the return grid.

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
cells span at least two filing families. Otherwise emit
`ABANDON_SEC_FORM4_INSIDER_FLOW_NO_VERSION_CREATED`.

## Terminal behavior and verification

No development or consumed period is loaded in this screen. No strategy version,
broker module, submit/cancel call, Paper activation, pool mutation, or order route
is allowed. A training pass authorizes only a separately reviewed development-data
acquisition proposal.

Tests must cover official table schemas, immutable resume, duplicate and
foreign-key rejection, P/S direction consistency, missing-value preservation,
exact CIK identity, shared CIKs, next-session availability, five-session expiry,
raw coverage inventory, 400-cell cardinality, training boundary, costs, delay,
and the no-execution invariants.
