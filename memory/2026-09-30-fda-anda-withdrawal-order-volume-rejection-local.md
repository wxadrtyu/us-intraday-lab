# Local fallback memory: FDA final ANDA withdrawal orders

summary: Federal Register 2021-2023 FDA final orders withdrawing approval of ANDAs were rejected at the source-event-volume gate. An official metadata-only query returned 48 generous title matches across 2021/2022/2023 (20/13/15), but that upper bound includes correction documents and mixed NDA/ANDA notices. The homogeneous original ANDA-only final-notice family contains only 32 documents (14/9/9), below the fixed 100-total and 20-each-year high-frequency source floor. No PDFs were acquired, no applicant mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-event-volume-gate

kpi_version: versionless-fda-anda-withdrawal-order-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-event-volume-gate, strategy:fda-anda-withdrawal-order, status:rejected, source:federal-register-fda, sample:coverage-limited-527

next_step: Audit Federal Register 2021-2023 FDA final determinations that a discontinued drug product was not withdrawn from sale for reasons of safety or effectiveness as a genuinely distinct statutory decision family. First prove an exact FDA/notice/title query, publication-date and GovInfo PDF identity, correction/republication links, and one homogeneous final-determination semantic; do not mix withdrawal orders, proposed decisions, safety withdrawals, NDA/ANDA approvals, shortages, enforcement, or animal-drug actions. Before any outcome read, count official documents and evaluate coverage using only the complete legal name of the NDA or ANDA holder expressly identified as the affected application holder and mechanically identical to a frozen SEC issuer. Do not map petitioners, drug or brand names, application numbers, manufacturers not identified as the holder, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. Freeze and switch if timing, document versioning, event semantics, source volume, or exact-name coverage cannot be proven.

## Frozen evidence

The official metadata-only upper bound is 48 documents, while the homogeneous original ANDA-only family is 32 documents with annual counts 14/9/9. `ABANDON_FDA_ANDA_WITHDRAWAL_ORDER_VOLUME_GATE`; `pdf_corpus_acquired=false`; `applicant_mapping_performed=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
