# NIH prospective exclusive patent-license notice volume rejection

Decision: **ABANDON_NIH_PROSPECTIVE_EXCLUSIVE_LICENSE_VOLUME_GATE**. The proposed 2021-2023 Federal Register family of National Institutes of Health prospective grants of exclusive patent licenses is frozen at the source-event-volume gate, before PDF acquisition, prospective-licensee matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for National Institutes of Health documents published from 2021-01-01 through 2023-12-31 with the term `Prospective Grant of an Exclusive Patent License`, ordered oldest first with a page size of 1,000. The search returned 68 documents.

The deliberately generous title upper bound accepts every title beginning exactly `Prospective Grant of an Exclusive Patent License`. It contains only **53 documents: 31 in 2021, 12 in 2022, and 10 in 2023**. One of the 2021 documents is explicitly a correction (`2021-05272`, *Engineered Tumor Infiltrating Lymphocytes; Correction*). Excluding that correction leaves at most **52 original notices: 30 in 2021, 12 in 2022, and 10 in 2023**.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/national-institutes-of-health
- https://www.federalregister.gov/documents/2021/01/14/2021-00637/
- https://www.federalregister.gov/documents/2022/03/01/2022-04245/
- https://www.federalregister.gov/documents/2023/01/20/2023-01019/

The fixed high-frequency source-design floor is 100 documents total and 20 in every training year. Even the deliberately broad 53-document title upper bound fails the total, 2022, and 2023 floors; the homogeneous original-notice family is smaller still. A correction is not a new license event. Patent, technology, field-of-use, or claim rows within one notice cannot be split into pseudo-events. Adding nonexclusive or partially exclusive licenses, cooperative research and development agreements, inventions available for licensing, government-use rights, final license documents, or other technology-transfer publications would destroy the predefined causal meaning.

Final state: `publication_identity_gate_passed=true`, `search_result_count=68`, `broad_title_upper_bound=53`, `broad_year_counts=31/12/10`, `homogeneous_original_notice_upper_bound=52`, `homogeneous_original_year_counts=30/12/10`, `source_volume_gate_passed=false`, `preregistered=false`, `pdf_corpus_acquired=false`, `prospective_licensee_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by counting a correction as a new event; splitting patents, technologies, fields of use, or claims; adding nonexclusive or partially exclusive licenses, CRADAs, inventions available for licensing, government-use rights, or final license documents; or mapping technology names, inventors, locations, collaborators, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
