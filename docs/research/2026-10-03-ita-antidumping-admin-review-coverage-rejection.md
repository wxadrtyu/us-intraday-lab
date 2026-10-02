# ITA antidumping administrative-review final-results coverage rejection

Decision: **ABANDON_ITA_AD_ADMIN_REVIEW_COVERAGE_GATE**. The 2021-2023 original final-results family is frozen before any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Contract correction and immutable source

An explicit-contract audit found that the earlier 257-document inventory retained 16 correction-titled notices and one additional `No-Shipments` spelling variant. This was a source-filter defect, not an observed-coverage adjustment. It was corrected before any return or post-availability outcome access by excluding `Correction`, `Corrected`, `No Shipments`, `No-Shipments`, and `Supersed` in addition to the already frozen amendment, court-decision, changed-circumstances, sunset, new-shipper, preliminary, countervailing, rescission, and no-shipment exclusions.

The corrected original-only inventory has **240 notices: 77 in 2021, 69 in 2022, and 94 in 2023**. All 240 Federal Register-linked GovInfo PDFs were fetched sequentially. The admissible manifest has SHA-256 `39b16863c7a9d5a14d8c27eab20a6cb3b796b9c9f04d8555057ccb6c25533214`, 48,080,100 bytes, 240 successful PDFs, zero failures, 240 distinct PDF hashes, and zero duplicate-byte groups. The previously downloaded excluded files remain in untracked state as audit evidence but are absent from the corrected manifest. The two broad official metadata pages, including correction and amendment evidence, remain frozen under their prior hashes.

## Decisive role-and-identity upper bound

The strict contract permits only a separately reviewed exporter or producer expressly named in a company-specific final-results table or equivalent determination and mechanically identical one-to-one to a frozen SEC issuer. Before doing role-specific extraction, an intentionally permissive superset searched every byte of extracted text from every admissible PDF for each one-to-one frozen SEC full legal-name key. This upper bound retains background, counsel, affiliate, petitioner, importer, and incidental mentions that the strict contract would reject. Therefore, strict reviewed-entity coverage can only be smaller.

The upper-bound artifact has SHA-256 `659f5a58e8c6571dcac19ac5c8d657536fb6db36aa98f4fdadecfa686f0e50bf`. It finds only:

- 4 distinct frozen issuers, below 10;
- 13 issuer-document pairs, below 50;
- 4/5/4 pairs in 2021/2022/2023, below 12 in every year;
- 2/3/3 issuers by year, below 5 in every year;
- 2 issuers with at least 3 events, below 6;
- a maximum issuer share of 46.15%, above 25%;
- 1 permissive pair without a later frozen sample session.

The four permissive issuer keys are ALB, CLF, STLD, and TSLA. These are not asserted to be separately reviewed exporters or producers. Because even the deliberately over-inclusive full-PDF mention superset fails every frozen coverage condition, role-specific extraction cannot pass and was not used to rescue the line.

Only `symbol` and `session_date` were read from the hash-verified event cube to enforce the 527-symbol identity/calendar boundary and next-session check. No return or outcome column was loaded. Final state: `pdf_corpus_acquired=true`, `admissible_pdfs=240`, `pdf_failures=0`, `duplicate_pdf_hash_groups=0`, `strict_role_mapping_performed=false`, `upper_bound_pairs=13`, `coverage_passed=false`, `event_cube_outcomes_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
