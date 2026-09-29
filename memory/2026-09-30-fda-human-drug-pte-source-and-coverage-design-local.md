# Local fallback memory: FDA human-drug PTE review-period source and coverage design

summary: The Federal Register 2021-2023 FDA regulatory-review-period determination source passed the source-volume gate for a preregistered human-drug-only family. The exact official API response is 406,578 bytes with SHA-256 a1c787cb19f47a9ab1037de56618559235897b772c6280df810e98361925e887. The frozen filter retains 103 original Notices whose titles begin with the exact determination prefix, exclude Correction, and whose abstracts identify a human drug product; annual counts are 27/21/55. The event is a procedural and quantified input to USPTO's later patent-term-extension decision, not an extension grant. Coverage thresholds and strict applicant-role/exact-issuer rules were frozen before PDF acquisition. No PDF, applicant map, event-cube outcome, or diagnostic cell was loaded.

stage: coverage-preregistration

kpi_version: versionless-fda-human-drug-pte-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:coverage-preregistration, strategy:fda-human-drug-pte-review-period, status:preregistered, source:federal-register-fda, sample:coverage-limited-527

next_step: Sequentially acquire and SHA-256 hash only the 103 frozen GovInfo PDFs, record missing/non-PDF/duplicate/correction conflicts, and extract only the complete legal entity expressly identified as the applicant for patent-term extension. Then apply the frozen exact one-to-one SEC issuer identity rule and next-session calendar using no post-publication outcome columns. Advance only if all frozen coverage conditions pass: 10 issuers, 50 symbol-document pairs, 12 pairs and 5 issuers in every year, 6 issuers with at least 3 documents, no issuer above 25%, and complete next-session availability. On any failure freeze `ABANDON_FDA_HUMAN_DRUG_PTE_COVERAGE_GATE`, leave cells_completed=0, and do not tune.

## Frozen evidence

`source_feasible=true`; `coverage_preregistered=true`; `human_drug_document_count=103`; `human_drug_year_counts=27/21/55`; `training_pdf_inventory_acquired=false`; `applicant_mapping_performed=false`; `event_cube_opened=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
