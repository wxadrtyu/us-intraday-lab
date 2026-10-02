# SEC original Form S-8 source audit and coverage preregistration

Status: **SOURCE_VOLUME_PASS; ACCEPTANCE_METADATA_COVERAGE_PENDING**. This is a source-and-coverage protocol only. The frozen event cube is a **527-symbol coverage-limited sample, not the full US market**, and no post-acceptance return or outcome may be opened before this protocol passes.

## Frozen family

The candidate family is one original EDGAR Form `S-8` accession filed by the issuer to register securities offered under employee-benefit plans. The event clock is the SEC acceptance datetime, not filing date, signature date, plan date, document date, or a news timestamp. Each accession is at most one issuer-document event.

The family excludes `S-8 POS`, every other registration form, resale registrations on other forms, 8-K, 10-K, proxy statements, press releases, amendments, withdrawals, and substitute filings. These sources cannot be mixed in to increase coverage. Later filings by the same issuer remain separate only when they have distinct original `S-8` accessions. No plan, share class, security, tranche, executive, or document section may be split into additional events.

Issuer identity is the filing CIK mechanically matched one-to-one to the frozen SEC issuer identity. Security-name inference, parent or subsidiary mapping, former names, abbreviations, fuzzy matching, and manual aliases are forbidden.

## Immutable source query

The complete source census is the 12 official quarterly EDGAR master archives at `https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.zip` for 2021-2023, filtered by exact form equality `S-8`. Archive byte counts and SHA-256 hashes are frozen in the audit artifact. The census finds 7,909 all-market original `S-8` accessions: 2,806 in 2021, 2,527 in 2022, and 2,576 in 2023. `S-8 POS` is separately observed at 5,375 and excluded.

The event-cube identity must be taken only from symbols present during the frozen 2021-2023 training window, not from symbols appearing elsewhere in the wider cube. That correction reduces the symbol boundary from an inadmissible 809-symbol all-period view to the frozen 527 symbols before acceptance acquisition. The frozen identity table within that boundary has one ambiguous CIK, 1652044, shared by GOOG and GOOGL. The one-to-one contract excludes that CIK rather than duplicating a filing across share classes. Corrected direct-CIK matching gives a deliberately permissive frozen-sample upper bound of 300 issuers and 620 issuer-accession pairs: 225/196/199 pairs and 180/166/165 issuers by year, 98 issuers with at least three events, and a maximum issuer share of 8/620. This passes the coarse metadata-only volume and concentration screen but does not pass the acceptance or document-identity gate.

## Pending acceptance and document-identity gate

For every one of the 620 upper-bound pairs, acquire the immutable official SEC filing-index HTML sequentially at `https://www.sec.gov/Archives/edgar/data/{CIK}/{accession-without-dashes}/{accession}-index.html` and freeze its URL, byte count, and SHA-256. The filing index is the metadata-only source for the accepted timestamp and document table; the full submission and primary-document body remain unopened at this gate. Parse and require:

- one accession number consistent with the master-index path;
- one valid SEC acceptance datetime;
- exactly one document block whose type is exactly `S-8`;
- a non-empty primary-document filename for that exact `S-8` block;
- a first frozen sample trading session strictly after the acceptance calendar date.

A failed filing-index fetch, malformed or inconsistent accession, missing acceptance datetime, zero or multiple exact-`S-8` primary-document rows, duplicate accession with conflicting bytes, or absent later frozen sample session is retained explicitly as missingness and excluded from the admissible pair set. Missing values are never imputed. Any systematic incompleteness, source inconsistency, or unresolvable version chain fails the family rather than being repaired with another source.

The admissible set must independently retain at least 10 issuers, 50 issuer-document pairs, at least 12 pairs and 5 issuers in each year, at least 6 issuers with 3 events, no issuer above 25%, and a later frozen sample session for every admitted pair. Acceptance coverage is checked before reading filing economics beyond the exact form/document identity and before any return.

Final preregistration state: `source_original_s8=7909`, `frozen_sample_symbols=527`, `ambiguous_ciks_excluded=1`, `coarse_sample_pairs=620`, `coarse_sample_issuers=300`, `acceptance_metadata_complete=false`, `coverage_passed=false`, `event_cube_columns_loaded=symbol/session_date`, `event_cube_outcomes_opened=false`, `cells_completed=0`, `post_acceptance_outcomes_loaded=false`.
