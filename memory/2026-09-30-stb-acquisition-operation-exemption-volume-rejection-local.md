# Local fallback memory: STB acquisition-and-operation exemptions

summary: Federal Register 2021-2023 Surface Transportation Board acquisition-and-operation exemption notices were rejected at the source-event-volume gate. The official broad search returned 108 documents, but the predefined homogeneous acquisition-and-operation title family contains only 29 notices across 2021/2022/2023 (11/5/13), below the fixed 100-total and 20-each-year high-frequency source floor. No PDFs were acquired, no acquiring-carrier mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-event-volume-gate

kpi_version: versionless-stb-acquisition-operation-exemption-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-event-volume-gate, strategy:stb-acquisition-operation-exemption, status:rejected, source:federal-register-stb, sample:coverage-limited-527

next_step: Audit Federal Register 2021-2023 FAA final special-conditions rules for novel aircraft, engine, or equipment designs as a genuinely different certification event family, strictly separate from the frozen final-airworthiness-directive and exemption-petition lines. Predefine one economically homogeneous original final-special-conditions family and do not mix proposed, supplemental, amended, corrected, withdrawn, equivalent-level-of-safety, exemption, or airworthiness-directive actions. Prove the exact FAA/type/title/action query, publication-date and GovInfo PDF identity, correction or supersession links, and the certification meaning of the rule. Before any outcome read, count official documents and evaluate coverage using only the applicant or type-certificate holder's complete legal name expressly stated in the final rule and mechanically identical to a frozen SEC issuer. Do not map aircraft or product names, models, divisions, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. Freeze and switch if public timing, document versioning, economic semantics, source volume, entity structure, or exact-name coverage cannot be proven.

## Frozen evidence

`ABANDON_STB_ACQUISITION_OPERATION_EXEMPTION_VOLUME_GATE`; `broad_search_result_count=108`; `homogeneous_notice_count=29`; `homogeneous_year_counts=11/5/13`; `pdf_corpus_acquired=false`; `acquiring_carrier_mapping_performed=false`; `event_cube_opened=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
