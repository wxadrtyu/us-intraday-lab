# NHTSA inconsequential-noncompliance grant volume rejection

Decision: **ABANDON_NHTSA_INCONSEQUENTIAL_GRANT_VOLUME_GATE**. The proposed 2021-2023 Federal Register family of final NHTSA decisions granting petitions for inconsequential noncompliance is frozen at the source-event-volume gate, before PDF acquisition, petitioner matching, event-cube access, or any post-publication return read. This family is distinct from, and does not reopen, the frozen NHTSA Safety Recalls and ODI investigation-opening lines. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for National Highway Traffic Safety Administration documents published from 2021-01-01 through 2023-12-31 with the term `Petition for Decision of Inconsequential`, ordered oldest first with a page size of 1,000. The broad search returned 149 documents, including petition-receipt notices, grants, denials, corrections, and unrelated term matches.

The predefined homogeneous final-grant family requires a title containing `Grant of Petition` or `Grant of Petitions` and `Inconsequential`. It contains only **27 final grant notices: 3 in 2021, 16 in 2022, and 8 in 2023**. The titles consistently identify the action as a grant of a petition for a decision of inconsequential noncompliance; the plural-petition title remains one Federal Register final-decision document, not multiple independently timed publications.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/national-highway-traffic-safety-administration
- https://www.federalregister.gov/documents/2021/01/04/2020-29042/
- https://www.federalregister.gov/documents/2022/01/19/2022-00869/
- https://www.federalregister.gov/documents/2023/03/07/2023-04662/

The fixed high-frequency source-design floor is 100 documents total and 20 in every training year. The homogeneous final-grant family fails the total floor and every annual floor. Adding denials, petition-receipt notices, corrections, recalls, ODI actions, technical service bulletins, consumer complaints, or unrelated term matches would destroy the predefined final-grant causal meaning. Multiple vehicles, standards, or petitions resolved in one final notice cannot be split into pseudo-events.

Final state: `publication_identity_gate_passed=true`, `broad_search_result_count=149`, `homogeneous_final_grant_count=27`, `homogeneous_year_counts=3/16/8`, `source_volume_gate_passed=false`, `preregistered=false`, `pdf_corpus_acquired=false`, `petitioner_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by mixing grants with denials or receipt notices; splitting vehicles, standards, products, or petitions within a document; adding recalls, ODI actions, technical service bulletins, consumer complaints, or corrections; or mapping brands, makes, models, products, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
