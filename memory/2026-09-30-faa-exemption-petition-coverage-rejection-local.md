# Local fallback memory: FAA exemption-petition notices

summary: Federal Register 2021-2023 FAA petition-for-exemption summary notices passed the source-volume screen with 147 original notices across 2021/2022/2023 (51/41/55) after excluding one correction, but failed a conservative issuer-coverage upper-bound gate. Strict title-petitioner equality against all current SEC issuers produced only 2 issuers and 2 pairs. An intentionally permissive all-current-SEC upper bound that removed THE and one legal suffix still produced only 7 issuers and 19 pairs, with annual pair/issuer counts 8/6, 2/1, and 9/2, below the fixed 10-issuer, 50-pair, and annual 12-pair/5-issuer floors. No PDFs were acquired, no frozen-527 mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: metadata-only-coverage-upper-bound

kpi_version: versionless-faa-exemption-petition-coverage-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:metadata-only-coverage-upper-bound, strategy:faa-exemption-petition-notice, status:rejected, source:federal-register-faa, sample:coverage-limited-527

next_step: Audit Federal Register 2021-2023 Surface Transportation Board acquisition-and-operation exemption notices as a genuinely different statutory transaction family. Predefine one economically homogeneous acquisition-and-operation exemption notice family and do not mix lease-and-operation, trackage-rights, continuance-in-control, merger, abandonment, construction, or final-decision actions. Prove the exact STB/type/title/action query, publication-date and GovInfo PDF identity, correction or withdrawal links, and the legal/economic meaning of the exemption notice. Before any outcome read, count official documents and evaluate coverage using only the acquiring carrier or applicant's complete legal name expressly stated in the notice and mechanically identical to a frozen SEC issuer. Do not map railroad reporting marks, line or route names, sellers, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. Freeze and switch if public timing, document versioning, economic semantics, source volume, entity structure, or exact-name coverage cannot be proven.

## Frozen evidence

`ABANDON_FAA_EXEMPTION_PETITION_COVERAGE_GATE`; `homogeneous_original_notice_count=147`; `homogeneous_year_counts=51/41/55`; `strict_all_current_sec_pairs=2`; `strict_all_current_sec_issuers=2`; `permissive_all_current_sec_pairs=19`; `permissive_all_current_sec_issuers=7`; `permissive_year_pairs_issuers=8/6,2/1,9/2`; `pdf_corpus_acquired=false`; `frozen_527_mapping_performed=false`; `event_cube_opened=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
