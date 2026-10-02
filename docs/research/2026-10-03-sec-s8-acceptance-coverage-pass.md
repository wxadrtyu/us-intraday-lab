# SEC original Form S-8 acceptance-coverage pass

Decision: **PASS_SEC_S8_ACCEPTANCE_COVERAGE_GATE**. This pass authorizes only a separately frozen 400-cell training design. It is not a strategy result, does not authorize development or consumed data, and does not authorize Paper or execution. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Immutable metadata corpus

The exact family remains original form type `S-8`; all 5,375 `S-8 POS` records and every other form remain excluded. SEC's official Form S-8 states that it registers securities offered under employee-benefit plans and becomes effective automatically upon filing. It also expressly allows a new Form S-8 for additional securities of the same class under an existing plan. The frozen event is therefore the issuer's accepted original S-8 registration accession, not a plan, security, tranche, or document-section pseudo-event. Official form reference: `https://www.sec.gov/servlet/sec/about/forms/forms-8.pdf`.

The 2021-2023 source census uses all 12 official EDGAR quarterly master indexes and retains 7,909 exact original S-8 accessions. The frozen 2021-2023 527-symbol boundary and one-to-one CIK rule yield 620 candidate issuer-accession pairs. CIK 1652044 is excluded because it maps to both GOOG and GOOGL in the frozen identity table.

All 620 official filing-index HTML pages were acquired sequentially with zero fetch failures. They total 5,277,737 bytes, have 620 distinct SHA-256 hashes, and have zero duplicate-byte groups. Each page has a master-path-consistent accession, a valid SEC accepted timestamp, and exactly one document-table row of type `S-8` with a non-empty primary-document filename. The full submissions and primary-document bodies remain unopened.

The acceptance-coverage artifact has SHA-256 `62943eb65d564e07960efcd206563adf1baebd5715d0c2db30a56cbe15be2ca8`.

## Honest sample availability and coverage

Availability begins on the first frozen sample trading session strictly after the SEC acceptance calendar date. Of 620 exact-CIK pairs, 138 have no later session for that symbol in the frozen 2021-2023 cube. They are retained as explicit end-censored or symbol-coverage missingness and excluded; they are not imputed, treated as cash, or replaced with another symbol.

The remaining 482 admissible issuer-document pairs pass every frozen metadata gate:

- 258 distinct issuers, above 10;
- 482 pairs, above 50;
- 220/150/112 pairs in 2021/2022/2023, above 12 in every year;
- 175/130/93 issuers by year, above 5 in every year;
- 62 issuers with at least 3 admissible events, above 6;
- maximum issuer share 8/482, or 1.66%, below 25%;
- every admitted pair has an acceptance timestamp, one exact S-8 primary-document identity, and a later frozen sample session.

Only `symbol` and `session_date` were read from the event cube. No return or post-acceptance outcome column was loaded. Final state: `filing_indexes_fetched=620`, `filing_index_failures=0`, `admissible_pairs=482`, `missing_next_session=138`, `coverage_passed=true`, `primary_document_bodies_opened=false`, `event_cube_outcomes_opened=false`, `cells_completed=0`, `post_acceptance_outcomes_loaded=false`.

Before any outcome access, the signal families, event lifetime, score direction, 400-cell grid, 9/18 bp costs, one-tier delay, retention gates, hashes, and missingness behavior must be written and approved as a separate frozen design. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
