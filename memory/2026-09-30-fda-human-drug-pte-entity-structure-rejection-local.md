# Local fallback memory: FDA human-drug PTE entity structure

summary: The preregistered Federal Register FDA human-drug patent-term-extension review-period family was rejected at the applicant-entity structure gate. All 103 frozen GovInfo PDFs were acquired successfully (22,104,470 bytes, 103 unique hashes; manifest SHA-256 477810956ff9025561c13a7575b44b560d6db41422fd64d65cc3b530bb71727e). Every target notice section was extracted, but none expressly names the legal entity filing the PTE application; the notices use only generic applicant references. Marketing applicants, NDA holders, sponsors, patent owners, assignees, agents, products, patents, and external USPTO joins cannot substitute for the frozen applicant role. No frozen-issuer mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: entity-structure-gate

kpi_version: versionless-fda-human-drug-pte-coverage-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:entity-structure-gate, strategy:fda-human-drug-pte-review-period, status:rejected, source:federal-register-fda, sample:coverage-limited-527

next_step: Audit Federal Register 2021-2023 National Institutes of Health prospective grants of exclusive patent licenses as a genuinely different official technology-transfer family. First define one economically homogeneous notice family and confirm publication-date/GovInfo identity, exact NIH agency/title query, correction or withdrawal chain, and whether the notice expressly states one prospective licensee's complete legal name. Do not mix nonexclusive licenses, cooperative research agreements, inventions available for licensing, government-use rights, or final license documents for volume. Before any outcome read, count official documents and evaluate coverage using only the expressly named prospective licensee mechanically identical to one frozen SEC issuer. Do not map technology names, inventors, licensee locations, research collaborators, subsidiaries, parents, former names, abbreviations, fuzzy matches, or manual aliases. Freeze and switch if timing, versioning, homogeneous volume, entity structure, or exact-name coverage cannot be proven.

## Frozen evidence

`ABANDON_FDA_HUMAN_DRUG_PTE_ENTITY_GATE`; `training_pdf_inventory_acquired=true`; `pdf_document_count=103`; `explicit_named_pte_applicants=0`; `frozen_527_mapping_performed=false`; `event_cube_opened=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
