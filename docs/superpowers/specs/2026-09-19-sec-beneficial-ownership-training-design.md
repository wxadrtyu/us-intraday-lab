# SEC Beneficial-Ownership Disclosure Training Design

## Objective and authorization

Test whether point-in-time Schedule 13D/13G beneficial-ownership disclosures
create an issuer-specific intraday continuation source in the fixed 527-symbol
2021-2023 training sample. The sample is coverage-limited and is never described
as full market. The standing research instruction authorizes moving immediately
from the frozen, rejected SEC 8-K line to a genuinely different causal mechanism
without asking for local tuning choices.

This is a versionless training-feasibility screen. It cannot authorize later-
period ranking, strategy admission, Paper activation, pool mutation, or order
routing.

## Alternatives and decision

Three free, auditable official sources were considered:

1. SEC Schedule 13D/13G disclosures: exact issuer CIK, acceptance timestamp,
   broad audited training coverage, and a distinct external-ownership mechanism.
2. SEC 13F information tables: broader institutional holdings but quarterly,
   delayed, manager-centric, and dependent on a historical CUSIP-to-symbol map
   not present in the frozen identity contract.
3. USPTO patent grants: economically distinct innovation events but require an
   unaudited assignee-to-issuer entity-resolution layer.

Use option 1. It is distinct from insider transactions: Form 4 reports trades by
officers, directors, and other insiders, whereas Schedules 13D/13G disclose
outside beneficial owners crossing or updating material ownership thresholds.
Do not combine this line with Form 4, 8-K, news, FINRA, Cboe, Federal Reserve,
CFTC, quote, or trade-print features.

## Official immutable source

Reuse the canonical SEC current-submission responses and exact declared
historical fragments already frozen for the SEC 8-K line. Their official source
is `https://data.sec.gov/submissions/`; every current response and historical
fragment has a URL, byte count, retrieval time, and SHA-256 record. No new
fragment names are synthesized and no filing documents or exhibits are fetched.

Validate the same required parallel arrays and preserve the canonical failed-v1
and accepted-v2 source evidence. A new normalized snapshot records its own
hashes while referring to the immutable source hashes. Missing, malformed,
duplicate, amended, and unmatched rows remain explicit rather than being filled
or silently discarded. Raw JSON, manifests, and caches stay outside Git.

## Fixed sample and identity

- The event cube SHA-256 is
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- It contains exactly 527 symbols observed during 2021-2023.
- Reuse the frozen exact SEC identity snapshot: 462 matched symbols and 65
  unmatched symbols. Preserve the unmatched set unchanged.
- Join only by exact numeric issuer CIK. Explicit shared-CIK share classes remain
  separate symbol events, while issuer coverage counts each CIK once.
- The current CIK association is retrospective feasibility evidence, not a
  historical security master or independent out-of-sample evidence.

## Qualifying filing and causal availability

The exact qualifying forms are `SC 13D`, `SC 13D/A`, `SC 13G`, and `SC 13G/A`.
Other ownership forms, 13F reports, blank forms, and document-derived guesses do
not qualify. Deduplicate only exact accession numbers; conflicting duplicates
fail closed.

Require filing date and SEC acceptance timestamp within 2021-2023. A filing
becomes usable only on the first sample session strictly after its acceptance
calendar date and stays active for that session plus the next four sample
sessions. This excludes every same-day signal, including pre-market acceptance.
Later amendments create new events but never rewrite an earlier event.

The metadata does not reveal signed ownership change, ownership percentage, or
reporting-owner identity reliably enough for this screen. Do not infer any of
those fields from form names, accession sequences, or price reactions.

## Frozen features and five families

For each issuer-session state, retain active accessions, exact forms, latest
acceptance timestamp, active filing count, days since latest filing, and a causal
20-session count of earlier qualifying ownership disclosures. The five strategy
families are:

1. original active-control disclosure (`SC 13D`) plus positive
   open-to-decision continuation;
2. active-control amendment (`SC 13D/A`) plus positive continuation;
3. original passive disclosure (`SC 13G`) plus positive continuation;
4. passive amendment (`SC 13G/A`) plus positive continuation;
5. clustered disclosure, requiring at least two causally available qualifying
   filings in the prior 20 sample sessions, plus positive continuation.

Each decision clock jointly ranks every causally covered eligible sample symbol.
Ties break by symbol. Portfolios are equal-weight, long-only, gross exposure at
most one, and flat at the frozen exit. Zero-signal sessions are valid. Filing
count and recency are audit fields, not additional tuned dimensions.

## Coverage gate

Before return evaluation, require:

- every canonical current response and required historical fragment to match its
  immutable source hash;
- at least 300 unique exact-mapped CIK issuers with at least three qualifying
  Schedule 13D/13G filings during training;
- at least 7,000 qualifying symbol-filing events;
- qualifying events in 2021, 2022, and 2023;
- no unexplained conflicting accession, parallel-array mismatch, source-hash
  mismatch, or missing canonical fragment.

Publish unique-CIK and symbol-event totals separately. If the gate fails, freeze
the evidence and emit `ABANDON_SEC_BENEFICIAL_OWNERSHIP_COVERAGE_GATE` without
running a return grid.

## Frozen grid and retention gates

- Decision bars: `2, 5, 11, 17, 23`.
- Holding bars: `1, 2, 4, 6`.
- Top counts: `1, 3, 5, 10`.
- Total: exactly 400 cells.
- Costs: 9 bp standard, 18 bp stress, and one-bar delayed entry at 9 bp.

Retain a cell only with at least 120 signal sessions, standard annualized return
at least 20%, information ratio at least 0.8, maximum drawdown below 20%, at
least two positive calendar years, positive 18 bp annualized return, and positive
delayed annualized return. Continue only if retained cells span at least two
families. Otherwise emit
`ABANDON_SEC_BENEFICIAL_OWNERSHIP_NO_VERSION_CREATED`.

## Failure handling and verification

Source-hash, schema, duplicate, timestamp, training-boundary, and identity
failures are preserved and fail closed. Tests cover exact form membership,
amendment treatment, conflicting duplicates, next-session availability,
five-session expiry, causal 20-session clustering, shared CIKs, raw coverage,
400-cell cardinality, cost/delay gates, and all no-execution invariants.

No development or consumed period is loaded. No strategy version, broker,
submit/cancel call, Paper activation, pool mutation, order route, or shutdown is
allowed. A training pass authorizes only a separately reviewed development-data
acquisition proposal.
