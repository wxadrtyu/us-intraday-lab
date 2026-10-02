# ITA antidumping administrative-review final-results source audit and coverage preregistration

Status: **SOURCE_FEASIBLE_AND_COVERAGE_PREREGISTERED**. This stage used only official Federal Register metadata and statutory-publication semantics. It did not acquire the 257 GovInfo PDFs, map reviewed exporters or producers to the frozen 527-symbol sample, open the event cube, or read any post-publication return. The sample remains a **527-symbol coverage-limited sample, not the full US market**.

## Frozen source family

The event is Federal Register publication of an original International Trade Administration final result of an antidumping-duty administrative review. Administrative-review final results establish review-period dumping margins and direct subsequent customs assessment and cash-deposit treatment. This is a completed periodic review action, not the previously frozen final affirmative less-than-fair-value investigation determination.

The official Federal Register API query is frozen as:

- agency: `international-trade-administration`
- publication date: `2021-01-01` through `2023-12-31`
- term: `Antidumping Duty Administrative Review Final Results`
- order: `oldest`
- page size: `1000`, following the official `next_page_url`

The two raw official API pages are retained in untracked state with SHA-256 values `e9398b7710f1d477c01d4641a0e0bf211f93179eba08ea27dddff1ae310b5e28` (2,508,076 bytes) and `e7f574ac380dbb7c2619ac81a7295d6a1d739aa0216e54d72f3e0211a158e6cc` (1,835,293 bytes). They contain 1,731 broad search results.

The deterministic homogeneous filter requires:

- `type=Notice`;
- title matching `Final Results of (the )?Antidumping Duty Administrative Review`, case-insensitively;
- title not containing `Amended`, `Court Decision`, `Changed Circumstances`, `Sunset`, `New Shipper`, `Preliminary`, `Countervailing`, `Rescission`, or `No Shipments`.

This produces **257 original final-results notices: 80 in 2021, 78 in 2022, and 99 in 2023**. Required publication date, document number, Federal Register page URL, and GovInfo PDF URL have zero missing values; document numbers have zero duplicates. The family passes the fixed high-frequency source floor of 100 total documents and 20 in every training year.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/international-trade-administration
- https://www.federalregister.gov/documents/2021/01/04/2020-29110/
- https://www.federalregister.gov/documents/2022/01/03/2021-28401/
- https://www.federalregister.gov/documents/2023/01/09/2023-00148/

Federal Register `publication_date` is the point-in-time public date. Only the GovInfo PDF addressed by the frozen `document_number` is admissible source content. Availability begins on the first frozen sample trading day strictly after publication. Corrections, amended results, court-remand notices, and later republications are audit links, never backfilled into the original event.

## Frozen entity and coverage rules

The only admissible exposed entity is a separately reviewed exporter or producer whose complete legal name is expressly stated in the final notice's company-specific final-results table or equivalent company-specific determination. Petitioners, domestic producers, importers, customs brokers, products, countries, rates, affiliates, non-selected companies, collapsed groups not individually named, no-shipment companies, and government entities are not exposed entities.

An event maps only when that complete reviewed-entity legal name is mechanically identical to exactly one frozen SEC issuer identity. No product or country inference, importer exposure, affiliate inference, subsidiary-to-parent or parent-to-subsidiary mapping, former-name substitution, acronym expansion, legal-name reconstruction, fuzzy match, external corporate-tree join, or hand-written alias is permitted. Multiple reviewed entities in one notice may create separate issuer-document pairs only when each entity independently satisfies the exact role and identity rule; the Federal Register document remains one source event for concentration and version auditing.

Before any outcome read, all 257 official GovInfo PDFs must be fetched sequentially and hash-frozen. Missing, non-PDF, duplicate-byte, correction, amendment, or supersession conflicts are preserved. The metadata-only coverage snapshot must then satisfy all of the following:

- at least 10 distinct frozen issuers;
- at least 50 exact issuer-document pairs;
- at least 12 pairs and 5 distinct issuers in each of 2021, 2022, and 2023;
- at least 6 issuers with 3 or more events;
- no single issuer above 25% of all retained pairs;
- every pair has a first frozen sample trading day strictly after publication.

Failure of any source, role, identity, calendar, annual, repetition, or concentration gate yields `ABANDON_ITA_AD_ADMIN_REVIEW_COVERAGE_GATE`, with `cells_completed=0` and no return access. Filters, roles, and thresholds may not be altered after observing coverage.

Final state for this stage: `source_complete=true`, `metadata_pages=2`, `broad_search_result_count=1731`, `homogeneous_notice_count=257`, `homogeneous_year_counts=80/78/99`, `required_metadata_missing=0`, `duplicate_document_numbers=0`, `coverage_preregistered=true`, `pdf_corpus_acquired=false`, `reviewed_entity_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
