# SEC exact original S-3ASR source preregistration

Status: **PREREGISTERED_METADATA_ONLY_SOURCE_AUDIT**.

## Economic family

The family is exact original EDGAR form type `S-3ASR`: an automatic shelf
registration statement filed by a well-known seasoned issuer under the SEC's
Securities Offering Reform framework. One issuer accession is one event. The
family is intentionally limited to the issuer's automatic shelf-registration
action and is not an offering, issuance, or capital-raised event.

The following are excluded before acquisition and cannot be added to rescue
coverage: `S-3ASR/A`, `S-3`, `S-3/A`, `EFFECT`, `424B5`, `FWP`, S-1 forms,
prospectus supplements, post-effective amendments, withdrawals, takedowns,
pricing notices, and manually linked financing transactions.

Official semantic sources:

- SEC EDGAR form index: <https://www.sec.gov/file/efmvol2-c3>
- Securities Offering Reform final rule: <https://www.sec.gov/files/rules/final/33-8591.pdf>
- Official Form S-3: <https://www.sec.gov/about/forms/forms-3.pdf>

## Immutable source and identity contract

- Census source: the 12 already-frozen official EDGAR quarterly
  `master.zip` archives for 2021-2023.
- Filter: byte-exact parsed form equality `S-3ASR`; amendments and every other
  form are counted separately and excluded.
- Identity: direct numeric CIK equality to the frozen SEC issuer snapshot,
  restricted to one-to-one CIK-to-symbol matches in the frozen 527-symbol
  sample. CIK 1652044 is excluded because it maps to GOOG and GOOGL.
- Forbidden identity rescue: security-name inference, parent/subsidiary,
  former name, abbreviation, fuzzy match, or manual alias.
- Immutable document identity: CIK, accession, filing date, official filing
  index URL, filing-index SHA-256, parsed accession, acceptance timestamp, and
  the unique primary-document row whose type is exactly `S-3ASR`.
- Availability: the first frozen sample session strictly after the SEC
  acceptance calendar date. Acceptance-day trading is never used.

The filing-index page may be acquired and parsed. Primary-document bodies,
exhibits, prospectuses, and linked filings remain unopened. The event cube may
be read only for `symbol` and `session_date`; every outcome column remains
closed.

## Frozen coarse upper bound

The complete official indexes contain 5,766 exact original `S-3ASR`
accessions: 2,165/1,508/2,093 by year. Direct one-to-one CIK matching gives a
coarse upper bound of 357 issuer-accession pairs across 295 issuers, with
126/95/136 pairs and 117/87/123 issuers by year. Eleven issuers have at least
three events and the largest issuer contributes 7/357 pairs, or 1.96%.

This upper bound passes the frozen source-coverage thresholds, but it does not
authorize outcome access. Missing pages, inconsistent accessions, absent
acceptance timestamps, non-unique exact primary rows, or absent later sample
sessions must be retained as explicit missingness and can only reduce coverage.

## Coverage gate

After all 357 official filing-index pages are fetched sequentially and hashed,
the admitted metadata-only set must have:

- at least 10 distinct issuers;
- at least 50 issuer-document pairs;
- at least 12 pairs and 5 issuers in each of 2021, 2022, and 2023;
- at least 6 issuers with 3 or more events;
- no issuer above 25% of pairs; and
- a later frozen sample session for every admitted pair.

Every requested page, HTTP/parse failure, byte count, SHA-256, duplicate-byte
group, accession mismatch, primary-row count, and missing next session is
retained. Any failed gate freezes the family without return access. A pass
allows a separate causal signal-design preregistration; it does not itself
authorize returns, development data, version creation, or execution.

Current state: `primary_document_bodies_opened=false`,
`event_cube_columns_allowed=symbol/session_date`,
`event_cube_opened_for_outcomes=false`, `cells_completed=0`,
`strategy_versions_created=0`, `paper_activation=false`, and
`order_route=FORBIDDEN`.
