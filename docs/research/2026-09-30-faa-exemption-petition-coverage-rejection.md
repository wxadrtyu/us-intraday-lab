# FAA exemption-petition notice coverage rejection

Decision: **ABANDON_FAA_EXEMPTION_PETITION_COVERAGE_GATE**. The 2021-2023 Federal Register family of Federal Aviation Administration summaries of petitions for exemption passes the source-volume screen but is frozen at a conservative issuer-coverage upper-bound gate, before PDF acquisition, frozen-527 mapping, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only source audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for Federal Aviation Administration documents published from 2021-01-01 through 2023-12-31 with the term `Petition for Exemption`, ordered oldest first with a page size of 1,000. The broad search returned 188 documents.

The homogeneous initial petition-receipt family requires `type=Notice` and a title beginning exactly `Petition for Exemption; Summary of Petition Received;`. This yields 148 title matches. One record has a correction document number (`C1-2021-19543`) and is not a new petition event. The original-notice family therefore contains **147 documents: 51 in 2021, 41 in 2022, and 55 in 2023**. It passes the fixed high-frequency source floor of 100 documents total and 20 in every training year.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/federal-aviation-administration
- https://www.federalregister.gov/documents/2021/01/21/2021-01223/
- https://www.federalregister.gov/documents/2022/03/02/2022-04349/
- https://www.federalregister.gov/documents/2023/12/14/2023-27503/

## Conservative all-current-SEC upper bound

Before any return access, the independent coverage floor was fixed at 10 issuers, 50 issuer-document pairs, at least 12 pairs and 5 issuers in every year, at least 6 issuers with 3 events, no issuer above 25% of pairs, and a next sample trading day for every retained document. Strict production mapping would use only the complete petitioner legal entity expressly stated in the notice and a one-to-one mechanically exact frozen-issuer identity.

The structural screen deliberately used a broader universe than the frozen sample: the official current SEC company-ticker file (SHA-256 `016ae8ffe06c0f8f8bed5aff9af1bb69ae12b197a3441851c712f88a5d7f64f1`). A strict punctuation-and-case equality between the title petitioner and an unambiguous SEC issuer produces only **2 issuers and 2 document pairs**. An intentionally permissive upper bound additionally removes `THE` and one terminal legal suffix while collapsing identical CIK/title rows across share classes. Even this overinclusive rule produces only **7 issuers and 19 document pairs**, with annual pair/issuer counts of **8/6, 2/1, and 9/2** for 2021/2022/2023. The matches are dominated by 13 Boeing notices and include names that strict complete-legal-entity equality would reject after suffix removal.

Because this permissive diagnostic covers all current SEC issuers rather than the frozen 527 identities and relaxes the exact-name rule, applying the frozen sample, point-in-time identity, full legal name, role, ambiguity, annual, concentration, and calendar requirements cannot create the missing issuers or pairs. Acquiring PDFs cannot rescue the monotone shortfall without substituting parents, subsidiaries, operators, brands, products, or aliases for the expressly named petitioner.

Final state: `publication_identity_gate_passed=true`, `broad_search_result_count=188`, `title_match_count=148`, `correction_count=1`, `homogeneous_original_notice_count=147`, `homogeneous_year_counts=51/41/55`, `source_volume_gate_passed=true`, `strict_all_current_sec_pairs=2`, `strict_all_current_sec_issuers=2`, `permissive_all_current_sec_pairs=19`, `permissive_all_current_sec_issuers=7`, `permissive_year_pairs_issuers=8/6,2/1,9/2`, `coverage_gate_passed=false`, `pdf_corpus_acquired=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by counting the correction as a new event; mixing grants, denials, renewals, amendments, withdrawals, rules, airworthiness directives, or exemption dispositions; or mapping aircraft or products, certificate numbers, operators, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
