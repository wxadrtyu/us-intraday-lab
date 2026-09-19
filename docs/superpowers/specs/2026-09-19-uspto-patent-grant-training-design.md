# USPTO Patent-Grant Event Training Design

## Objective and authorization

Test whether public U.S. patent grants create a short issuer-specific intraday
continuation source in the fixed 527-symbol 2021-2023 training sample. The
sample is coverage-limited and is never described as full market. This line is
economically distinct from the frozen news, FINRA, Cboe, Federal Reserve,
CFTC, SEC filing, insider, material-event, and beneficial-ownership families.

This is a versionless training-feasibility screen. It cannot authorize later-
period ranking, strategy admission, Paper activation, pool mutation, or order
routing.

## Source alternatives and decision

Three source paths were evaluated:

1. The current USPTO Open Data Portal PatentsView products. This is the current
   official distribution, but since June 18, 2026 the portal requires a signed-
   in USPTO.gov account and API key. No account creation, login, or key creation
   is authorized by this research task.
2. The immutable USPTO-authored PatentsView final metadata release archived at
   Zenodo DOI `10.5281/zenodo.15058362`. It is public, versioned, independently
   downloadable by file, and covers grants through December 31, 2024.
3. Weekly raw USPTO grant XML. It is official and point-in-time, but the current
   bulk portal has the same account boundary and would add a large XML parser
   without improving the strict issuer mapping used here.

Use option 2. Download only `g_patent.tsv.zip` and
`g_assignee_not_disambiguated.tsv.zip` from record `15058362`. The publisher
lists MD5 `f74fbde4b2adbf980b8e4ed5394f16d2` for the patent file and MD5
`6154c6d989206de65b1367b886f744d3` for the assignee file. Preserve the exact
record URL, file URL, byte count, publisher MD5, retrieval timestamp, and local
SHA-256. Raw archives, extracted tables, manifests, and caches stay outside
Git. If either archive cannot be fetched or does not match the publisher MD5,
freeze the failure and abandon the line without substituting another mirror.

The archive is official-authored research data, not the legal USPTO record.
Its assignee records and SEC issuer names are retrospective feasibility inputs,
not a point-in-time security master or independent out-of-sample evidence.

## Fixed sample and strict issuer mapping

- The event cube SHA-256 is
  `399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`.
- It contains exactly 527 symbols observed during 2021-2023.
- Reuse the frozen SEC ticker snapshot. Preserve the existing 65 symbols that
  lack an exact SEC identity, plus every additional patent-assignee mismatch.
- Use the SEC issuer `title` and the raw, non-disambiguated PatentsView assignee
  organization name. Do not use PatentsView's model-derived assignee identity.
- Canonicalization is mechanical and frozen: Unicode NFKC; uppercase; replace
  punctuation with spaces; collapse whitespace; and remove only terminal legal
  suffix tokens from the closed set `INC`, `INCORPORATED`, `CORP`,
  `CORPORATION`, `CO`, `COMPANY`, `LTD`, `LIMITED`, `LLC`, `LP`, and `PLC`.
- Accept a mapping only when the canonical key is unique among SEC issuer
  titles and unique among raw assignee organization names. Reject collisions,
  individuals, governments, universities, subsidiaries, former names, aliases,
  acronyms, translations, manual overrides, and fuzzy or semantic matches.
- Explicit shared-issuer share classes remain separate symbol events. Patent
  coverage counts the issuer once and symbol-patent events once per explicit
  symbol.

Every raw assignee name, normalized key, accepted match, collision, and
unmatched reason is retained. This intentionally sacrifices coverage to avoid
invented issuer links.

## Grant event and causal availability

Join the raw assignee table to the patent table only by exact `patent_id`.
Qualifying rows are granted patents with a valid public grant date from
2021-01-01 through 2023-12-31 and an accepted strict issuer mapping. Deduplicate
only exact `(patent_id, assignee_sequence)` rows; conflicting patent metadata
fails closed.

The grant date is the public issue date. A patent becomes usable only on the
first sample session strictly after its grant date and remains active for that
session plus the next four sample sessions. Same-day use is forbidden even
when the grant date is a trading day. Later source revisions never rewrite an
earlier causal timestamp in this frozen snapshot.

## Frozen features and five families

For each issuer-session state, retain active patent IDs, public grant dates,
same-day grant count, active patent count, days since latest grant, prior
60-session grant count, prior 60-session median nonzero batch size, raw issuer
patent inventory, and explicit coverage reason. The five positive
open-to-decision continuation families are:

1. singleton grant batch: exactly one patent on the public grant date;
2. small grant cluster: two through four patents on the public grant date;
3. large grant cluster: at least five patents on the public grant date;
4. accelerating grant batch: current batch count exceeds both one and the
   median nonzero batch size from the strictly prior 60 sample sessions;
5. resumed innovation: the current grant batch follows 60 complete sample
   sessions with no qualifying patent grant.

The trailing features use only availability sessions at or before the current
event state and never future grants. Batch count and recency are audit fields,
not tunable dimensions. Each decision clock jointly ranks every causally
covered eligible sample symbol, ties break by symbol, portfolios are
equal-weight and long-only, gross exposure is at most one, and positions are
flat at the frozen exit. Zero-signal sessions are valid.

## Coverage gate

Before any return evaluation, require:

- both exact publisher files present, publisher MD5 matched, and local SHA-256
  recorded;
- at least 100 uniquely exact-mapped issuers with at least three qualifying
  patents during training;
- at least 5,000 qualifying symbol-patent events;
- qualifying events in 2021, 2022, and 2023;
- no unexplained archive, schema, duplicate, date, identity-collision, or join
  failure.

Publish issuer, symbol, patent, collision, and unmatched totals separately. If
the gate fails, freeze the evidence and emit
`ABANDON_USPTO_PATENT_GRANT_COVERAGE_GATE` without running a return grid.

## Frozen grid and retention gates

- Decision bars: `2, 5, 11, 17, 23`.
- Holding bars: `1, 2, 4, 6`.
- Top counts: `1, 3, 5, 10`.
- Total: exactly 400 cells.
- Costs: 9 bp standard, 18 bp stress, and one-bar delayed entry at 9 bp.

Retain a cell only with at least 120 signal sessions, standard annualized return
at least 20%, information ratio at least 0.8, maximum drawdown below 20%, at
least two positive calendar years, positive 18 bp annualized return, and
positive delayed annualized return. Continue only if retained cells span at
least two families. Otherwise emit
`ABANDON_USPTO_PATENT_GRANT_NO_VERSION_CREATED`.

## Failure handling and verification

Archive-hash, schema, duplicate, grant-date, training-boundary, issuer-key,
identity-collision, and patent-join failures are preserved and fail closed.
Tests cover mechanical issuer canonicalization, one-to-one mapping, ambiguous
and unmatched preservation, archive hashes, patent joins, next-session
availability, five-session expiry, causal 60-session features, raw coverage,
400-cell cardinality, cost/delay gates, and all no-execution invariants.

No development or consumed period is loaded. No strategy version, broker,
submit/cancel call, Paper activation, pool mutation, order route, API-key
creation, USPTO account action, or shutdown is allowed. A training pass
authorizes only a separately reviewed development-data acquisition proposal.
