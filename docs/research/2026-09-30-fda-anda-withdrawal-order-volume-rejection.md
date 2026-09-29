# FDA final ANDA withdrawal-order volume rejection

Decision: **ABANDON_FDA_ANDA_WITHDRAWAL_ORDER_VOLUME_GATE**. The proposed 2021-2023 Federal Register family of final FDA orders withdrawing approval of abbreviated new drug applications is frozen at the source-event-volume gate, before PDF acquisition, applicant matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official metadata-only audit

Federal Register publication dates, document numbers, official document pages, and GovInfo PDFs provide a viable statutory-publication identity. The official Federal Register API was queried for Food and Drug Administration documents published from 2021-01-01 through 2023-12-31 with the term `Withdrawal of Approval`. The broad current-title diagnostic returned 229 documents of many unrelated kinds.

A deliberately generous title upper bound for documents mentioning withdrawal of approval of one or more abbreviated new drug applications produced 48 documents: 20 in 2021, 13 in 2022, and 15 in 2023. That upper bound still includes correction documents and mixed NDA/ANDA notices. Applying the preregisterable homogeneous-document rule—exclude titles ending in `Correction` and exclude documents jointly withdrawing NDAs and ANDAs—leaves only **32 original ANDA-only final notices: 14 in 2021, 9 in 2022, and 9 in 2023**.

Official sources:

- https://www.federalregister.gov/api/v1/documents.json
- https://www.federalregister.gov/agencies/food-and-drug-administration
- https://www.federalregister.gov/documents/2021/03/05/2021-04520/
- https://www.federalregister.gov/documents/2022/05/20/2022-10924/
- https://www.federalregister.gov/documents/2023/12/19/2023-27853/

The fixed high-frequency source-design floor is 100 documents total and 20 in every training year. The homogeneous family fails both conditions by a wide margin. ANDA rows within one notice are consequences grouped into one legal publication and cannot be split into pseudo-events. Corrections cannot be counted as independent economic shocks or merged backward without a separately frozen correction policy.

Final state: `publication_identity_gate_passed=true`, `broad_title_upper_bound=48`, `broad_year_counts=20/13/15`, `homogeneous_original_document_count=32`, `homogeneous_year_counts=14/9/9`, `source_volume_gate_passed=false`, `preregistered=false`, `pdf_corpus_acquired=false`, `applicant_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_publication_outcomes_loaded=false`. Do not reopen by counting ANDA or product table rows, corrections, mixed NDA/ANDA notices, proposed withdrawals, NDA withdrawals, biologics, safety communications, shortages, enforcement actions, or approval actions. Do not map drug names, labels, application numbers, non-applicant manufacturers, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
