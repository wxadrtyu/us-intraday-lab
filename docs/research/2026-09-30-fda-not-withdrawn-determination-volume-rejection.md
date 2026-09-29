# FDA not-withdrawn safety/effectiveness determination volume rejection

Decision: **ABANDON_FDA_NOT_WITHDRAWN_DETERMINATION_VOLUME_GATE**. The proposed 2021-2023 Federal Register family of final FDA determinations that a discontinued drug was not withdrawn from sale for reasons of safety or effectiveness is frozen at the source-event-volume gate, before PDF acquisition, application-holder matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for Food and Drug Administration documents published from 2021-01-01 through 2023-12-31 with `Not Withdrawn From Sale`. The search returned 91 documents, including unrelated rules and guidance, actual safety withdrawals, a proposed withdrawal, and a mixed determination.

The deliberately generous homogeneous title upper bound accepts `Was Not`, `Were Not`, and `Has Not Been` withdrawn from sale for reasons of safety or effectiveness, excludes correction titles, and excludes the mixed `Except ... Which Was Withdrawn` determination. It contains only **69 documents: 21 in 2021, 17 in 2022, and 31 in 2023**.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/food-and-drug-administration
- https://www.federalregister.gov/documents/2021/01/08/2021-00118/
- https://www.federalregister.gov/documents/2022/01/18/2022-00832/
- https://www.federalregister.gov/documents/2023/01/18/2023-00792/

The fixed high-frequency source-design floor is 100 documents total and 20 in every training year. Even this generous upper bound fails the total floor and the 2022 annual floor. Multiple products or dosage strengths named in one determination remain one legal publication and cannot be split into pseudo-events. Adding actual safety withdrawals, proposed actions, mixed findings, animal-drug actions, approvals, shortages, or unrelated search hits would destroy the predefined causal meaning.

Final state: `publication_identity_gate_passed=true`, `search_result_count=91`, `homogeneous_title_upper_bound=69`, `homogeneous_year_counts=21/17/31`, `source_volume_gate_passed=false`, `preregistered=false`, `pdf_corpus_acquired=false`, `application_holder_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by splitting products, strengths, applications, or table rows; adding actual withdrawals, proposed decisions, mixed findings, withdrawal orders, approvals, shortages, enforcement, animal-drug actions, corrections, or unrelated API hits; or mapping petitioners, drug or brand names, application numbers, non-holder manufacturers, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
