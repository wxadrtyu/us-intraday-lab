# FAA final special-conditions volume rejection

Decision: **ABANDON_FAA_FINAL_SPECIAL_CONDITIONS_VOLUME_GATE**. The proposed 2021-2023 Federal Register family of FAA final special-conditions rules for novel aircraft, engine, or equipment designs is frozen at the source-event-volume gate, before PDF acquisition, applicant or type-certificate-holder matching, event-cube access, or any post-publication return read. This family is distinct from, and does not reopen, the frozen FAA final-airworthiness-directive and exemption-petition lines. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for Federal Aviation Administration documents published from 2021-01-01 through 2023-12-31 with the term `Special Conditions`, ordered oldest first with a page size of 1,000. The broad search returned 428 documents, including instrument-procedure rules, airworthiness directives, proposed rules, notices, and other unrelated term matches.

The deliberately generous final-rule title upper bound requires `type=Rule` and a title beginning exactly `Special Conditions:`. It contains only **71 documents: 20 in 2021, 37 in 2022, and 14 in 2023**. This upper bound does not yet remove any supplemental, amended, corrected, superseding, or otherwise non-original rule whose status may be disclosed only in the body; the predefined original final-special-conditions family can therefore only be smaller.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/federal-aviation-administration
- https://www.federalregister.gov/documents/2021/02/02/2021-02139/
- https://www.federalregister.gov/documents/2022/01/10/2022-00096/
- https://www.federalregister.gov/documents/2023/02/27/2023-03980/

The fixed high-frequency source-design floor is 100 documents total and 20 in every training year. Even the generous 71-document title upper bound fails the total floor and the 2023 annual floor. Adding proposed, supplemental, amended, corrected, withdrawn, equivalent-level-of-safety, exemption, airworthiness-directive, or unrelated rule actions would destroy the predefined original final-special-conditions causal meaning. Multiple aircraft models, systems, design features, or special conditions in one rule remain one statutory publication and cannot be split into pseudo-events.

Final state: `publication_identity_gate_passed=true`, `broad_search_result_count=428`, `generous_final_rule_title_upper_bound=71`, `upper_bound_year_counts=20/37/14`, `source_volume_gate_passed=false`, `preregistered=false`, `pdf_corpus_acquired=false`, `applicant_or_holder_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by mixing original final rules with proposed, supplemental, amended, corrected, withdrawn, equivalent-level-of-safety, exemption, or airworthiness-directive actions; splitting models, systems, features, conditions, or docket components; or mapping aircraft or product names, models, divisions, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
