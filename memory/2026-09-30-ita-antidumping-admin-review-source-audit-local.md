# Local fallback memory: ITA antidumping administrative-review final results

summary: Federal Register 2021-2023 ITA original final results of antidumping-duty administrative reviews passed the source-volume audit and received a frozen pre-outcome coverage design. Two official API pages hash to e9398b7710f1d477c01d4641a0e0bf211f93179eba08ea27dddff1ae310b5e28 and e7f574ac380dbb7c2619ac81a7295d6a1d739aa0216e54d72f3e0211a158e6cc. The fixed notice/title/exclusion filter yields 257 documents across 2021/2022/2023 (80/78/99), with zero missing required metadata and zero duplicate document numbers. Only a separately reviewed exporter or producer expressly named in the final company-specific results may map by one-to-one exact frozen issuer identity. No PDFs or outcomes have been loaded and cells_completed is zero.

stage: source-audit-and-coverage-preregistration

kpi_version: versionless-ita-ad-admin-review-coverage-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-audit-and-coverage-preregistration, strategy:ita-ad-admin-review-final-results, status:coverage-preregistered, source:federal-register-ita, sample:coverage-limited-527

next_step: Sequentially acquire and SHA-256 hash all 257 frozen GovInfo PDFs, preserving missing, non-PDF, duplicate-byte, correction, amendment, and supersession evidence. Extract only separately reviewed exporter or producer complete legal names from company-specific final-results tables or equivalent determinations. Then run the frozen metadata-only coverage gate: at least 10 issuers, 50 issuer-document pairs, 12 pairs and 5 issuers in each year, 6 issuers with at least 3 events, no issuer above 25%, and a next sample trading day for every pair. Do not load returns before every coverage condition passes. Do not use products, countries, rates, petitioners, domestic producers, importers, affiliates, non-selected companies, collapsed groups not individually named, subsidiaries, parents, former names, abbreviations, fuzzy matches, external corporate trees, or manual aliases.

## Frozen evidence

`homogeneous_notice_count=257`; `homogeneous_year_counts=80/78/99`; `required_metadata_missing=0`; `duplicate_document_numbers=0`; `coverage_preregistered=true`; `pdf_corpus_acquired=false`; `reviewed_entity_mapping_performed=false`; `event_cube_opened=false`; `cells_completed=0`; `post_publication_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
