# STB acquisition-and-operation exemption volume rejection

Decision: **ABANDON_STB_ACQUISITION_OPERATION_EXEMPTION_VOLUME_GATE**. The proposed 2021-2023 Federal Register family of Surface Transportation Board acquisition-and-operation exemption notices is frozen at the source-event-volume gate, before PDF acquisition, acquiring-carrier matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for Surface Transportation Board documents published from 2021-01-01 through 2023-12-31 with the term `Acquisition and Operation Exemption`, ordered oldest first with a page size of 1,000. The broad search returned 108 documents, including acquisition-and-operation notices, change-of-operator notices, trackage rights, continuance-in-control, merger, lease, abandonment, rules, and unrelated term matches.

The predefined homogeneous transaction family requires `type=Notice` and a title structured as `[acquiring carrier]-Acquisition and Operation Exemption-[counterparty or line]`, without change-of-operator, lease, trackage-rights, continuance-in-control, merger, abandonment, construction, or other action language. It contains only **29 notices: 11 in 2021, 5 in 2022, and 13 in 2023**.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/surface-transportation-board
- https://www.federalregister.gov/documents/2021/02/12/2021-02846/
- https://www.federalregister.gov/documents/2022/03/25/2022-06338/
- https://www.federalregister.gov/documents/2023/02/17/2023-03471/

The fixed high-frequency source-design floor is 100 documents total and 20 in every training year. The homogeneous family fails the total floor and every annual floor. Adding change-of-operator, lease-and-operation, trackage-rights, continuance-in-control, merger, abandonment, construction, rules, final decisions, or unrelated term matches would destroy the predefined acquisition-and-operation causal meaning. A notice naming multiple lines, counties, counterparties, or assets remains one statutory publication and cannot be split into pseudo-events.

Final state: `publication_identity_gate_passed=true`, `broad_search_result_count=108`, `homogeneous_notice_count=29`, `homogeneous_year_counts=11/5/13`, `source_volume_gate_passed=false`, `preregistered=false`, `pdf_corpus_acquired=false`, `acquiring_carrier_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by mixing acquisition-and-operation notices with change-of-operator, lease, trackage-rights, continuance-in-control, merger, abandonment, construction, rules, or final decisions; splitting lines, routes, counties, counterparties, assets, or docket components; or mapping railroad reporting marks, line or route names, sellers, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
