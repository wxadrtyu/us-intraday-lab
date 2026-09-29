# FRA waiver-petition notice volume rejection

Decision: **ABANDON_FRA_WAIVER_PETITION_NOTICE_VOLUME_GATE**. The proposed 2021-2023 Federal Register family of Federal Railroad Administration notices of petitions for waiver of compliance is frozen at the source-event-volume gate, before PDF acquisition, petitioner matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for Federal Railroad Administration documents published from 2021-01-01 through 2023-12-31 with the term `Petition for Waiver of Compliance`, ordered oldest first with a page size of 1,000. The search returned 191 documents, including original petitions, extensions, amendments, expansions, modifications, comment-period actions, rules, and unrelated term matches.

The predefined homogeneous new-petition notice family requires the title to equal `Petition for Waiver of Compliance`. It contains only **88 notices: 46 in 2021, 19 in 2022, and 23 in 2023**. Extension, amendment, expansion, modification, statutory-exemption, reopening, and comment-period notices are later or legally different actions and are not interchangeable with a new waiver petition.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/federal-railroad-administration
- https://www.federalregister.gov/documents/2021/01/08/2021-00141/
- https://www.federalregister.gov/documents/2022/02/16/2022-03287/
- https://www.federalregister.gov/documents/2023/12/21/2023-28110/

The fixed high-frequency source-design floor is 100 documents total and 20 in every training year. The homogeneous exact-title family fails the total floor and the 2022 annual floor. Adding extensions, amendments, expansions, modifications, statutory exemptions, comment-period actions, final decisions, safety advisories, emergency orders, accident reports, enforcement actions, or unrelated search hits would destroy the predefined new-petition causal meaning. Multiple routes, facilities, vehicles, or requested provisions within one notice cannot be split into pseudo-events.

Final state: `publication_identity_gate_passed=true`, `broad_search_result_count=191`, `homogeneous_exact_title_count=88`, `homogeneous_year_counts=46/19/23`, `source_volume_gate_passed=false`, `preregistered=false`, `pdf_corpus_acquired=false`, `petitioner_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by mixing original petitions with extensions, amendments, expansions, modifications, statutory exemptions, comment-period actions, or final decisions; splitting routes, facilities, equipment, requested provisions, or docket components; adding safety advisories, emergency orders, accident reports, or enforcement actions; or mapping railroad reporting marks, routes, facility or equipment names, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
