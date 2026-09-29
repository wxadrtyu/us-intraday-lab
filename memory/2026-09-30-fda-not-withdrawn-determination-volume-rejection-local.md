# Local fallback memory: FDA not-withdrawn safety/effectiveness determinations

summary: Federal Register 2021-2023 FDA final determinations that discontinued drug products were not withdrawn for reasons of safety or effectiveness were rejected at the source-event-volume gate. The official search returned 91 documents, but the generous homogeneous title upper bound contains only 69 final determinations across 2021/2022/2023 (21/17/31), below the fixed 100-total and 20-each-year high-frequency source floor. No PDFs were acquired, no application-holder mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-event-volume-gate

kpi_version: versionless-fda-not-withdrawn-determination-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-event-volume-gate, strategy:fda-not-withdrawn-determination, status:rejected, source:federal-register-fda, sample:coverage-limited-527

next_step: Audit Federal Register 2021-2023 FDA determinations of regulatory review periods for patent-term extension applications as a genuinely different statutory publication family. First predefine one economically homogeneous human-drug determination family and exclude medical devices, biologics, veterinary products, correction notices, patent-extension grants, petitions, and approval announcements. Prove exact FDA/notice/title query reproduction, publication-date and GovInfo PDF identity, correction/republication links, and the statutory role of the determination. Before any outcome read, count official documents and evaluate coverage using only the complete legal name of the patent-term-extension applicant or application holder expressly identified in the notice and mechanically identical to a frozen SEC issuer. Do not map product or brand names, patent numbers, application numbers, agents, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. Freeze and switch if public timing, document versioning, economic semantics, source volume, or exact-name coverage cannot be proven.

## Frozen evidence

The official metadata-only homogeneous upper bound is 69 documents with annual counts 21/17/31. `ABANDON_FDA_NOT_WITHDRAWN_DETERMINATION_VOLUME_GATE`; `pdf_corpus_acquired=false`; `application_holder_mapping_performed=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
