# SEC direct-form screen and Form SD source preregistration

## Metadata-only screen

After freezing the rejected S-3ASR training result, the next-source screen
reused the 12 immutable official EDGAR quarterly master indexes, the frozen SEC
identity snapshot, and only `symbol/session_date` from the immutable event
container. It computed direct one-to-one CIK upper bounds for every exact form
type without loading an outcome column.

The untracked complete screen is
`state/sec_direct_form_screen/coarse-form-screen.json`, SHA-256
`c9bfb5fb1755850a0ac3aa2256397513a6d6148a9ddf200555e92052ba51e879`.
Already frozen 8-K, Form 4, periodic fundamentals, beneficial ownership, S-8,
and S-3ASR families remain excluded. Form 144 is not selected because its
electronic master-index coverage changes from 22/52 pairs in 2021/2022 to 5,835
in 2023, so the proposed history is not a stable comparable source regime.

## Selected family and legal ambiguity

Exact original Form `SD` has a frozen-sample coarse upper bound of 538 pairs
across 185 issuers, with 176/180/182 pairs and 176/180/182 issuers by year. 173
issuers have at least three filings and maximum concentration is 3/538, or
0.558%. The complete official indexes contain 3,049 exact `SD` rows.

Form SD is not homogeneous by form code alone. The official form contains Rule
13p-1 conflict-minerals disclosure and Rule 13q-1 resource-extraction payment
disclosure. The SEC's 2020 resource-extraction rule states that issuers begin
compliance for fiscal years ending no earlier than two years after the March
16, 2021 effective date; a December-year-end issuer's example first deadline is
September 30, 2024. This strongly suggests 2021-2023 filings are primarily
conflict-minerals reports, but source semantics will not be assumed from date.

Official evidence:

- Form SD: <https://www.sec.gov/files/formsd.pdf>
- Resource-extraction final rule and transition:
  <https://www.sec.gov/files/rules/final/2020/34-90679.pdf>

## Preregistered immutable audit

The audit includes exact original `SD` only and excludes `SD/A` and every other
form. Identity is direct one-to-one numeric CIK matching; CIK 1652044 and every
other shared-CIK ambiguity are excluded. No name, security, parent/subsidiary,
former-name, fuzzy, or manual mapping is allowed.

For every coarse pair, acquire sequentially and hash:

1. the official filing-index page, requiring matching accession, SEC acceptance
   timestamp, and exactly one primary-document row whose type is exactly `SD`;
2. that exact primary document, retaining its URL, byte count, SHA-256, and all
   failures; and
3. a mechanical legal-subtype classification from the primary body's explicit
   Rule 13p-1/Rule 13q-1 and Section/Item labels.

An admissible `conflict_minerals_original` event must affirmatively reference
Rule 13p-1 and Item 1.01 conflict-minerals disclosure. It must not affirmatively
select Rule 13q-1 or contain an applicable Item 2.01 resource-extraction report.
A resource-extraction filing, dual-applicable filing, amendment, ambiguous
checkbox/text state, absent primary row, missing timestamp, mismatched
accession, duplicate conflict, or unparseable document is excluded and retained
as explicit evidence. Classification must not use issuer industry, filing date,
manual review, or an outcome.

Availability is the first frozen sample session strictly after the SEC
acceptance calendar date. Same-day use is forbidden. The event cube remains
limited to `symbol/session_date` through this stage.

## Frozen coverage gate

After legal-subtype classification and next-session mapping, the original
conflict-minerals family must retain at least 10 issuers, 50 pairs, at least 12
pairs and 5 issuers in each year, at least 6 issuers with three events, no issuer
above 25%, and a later frozen sample session for every admitted pair. The audit
also reports filing-date concentration and the maximum possible unique active
calendar sessions for a three-session event life. If the existing 120-signal-
session training floor is structurally unreachable, the family is rejected at
design before outcomes rather than lowering the floor.

No outcome, exhibit, conflict-minerals report attachment, issuer website,
development/consumed period, strategy version, monitoring/Paper state, broker,
or order route is opened or changed by this source audit.
