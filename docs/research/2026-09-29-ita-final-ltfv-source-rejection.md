# ITA final affirmative LTFV source rejection

Decision: **ABANDON_ITA_FINAL_AFFIRMATIVE_LTFV_SOURCE**. The proposed 2021–2023 International Trade Administration final affirmative less-than-fair-value determination line is frozen at the source-volume design gate, before preregistration, PDF acquisition, exporter/producer matching, event-cube access, or any post-publication return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Point-in-time source contract

The publication channel itself is suitable. The admissible event would have been the official GovInfo Federal Register PDF identified by stable Federal Register `document_number`, with availability conservatively set to the first frozen-sample trading session strictly after `publication_date`. FederalRegister.gov HTML, public-inspection copies, Trade.gov summaries, later orders, and later amended or corrected determinations would not have substituted for the publication PDF.

The economic event is also coherent: a final affirmative antidumping determination is Commerce's final finding that investigated merchandise was sold at less than fair value. It remains distinct from countervailing-duty determinations, preliminary determinations, administrative or sunset reviews, scope and circumvention rulings, court remands, amended determinations, and antidumping-duty orders.

Official references:

- Federal Register API documentation: https://www.federalregister.gov/developers/documentation/api/v1
- Official Federal Register collection on GovInfo: https://www.govinfo.gov/app/collection/FR
- International Trade Administration final-determination FAQ: https://www.trade.gov/faq/faqs-final-determination-antidumping-duty-andor-countervailing-duty-investigation

## Economically homogeneous family screen

One complete read-only official API response was requested for International Trade Administration notices published from 2021-01-01 through 2023-12-31, using the full-text term `Final Affirmative Determination of Sales at Less Than Fair Value`, `per_page=1000`, and oldest-first ordering. The broad API search returned 574 records because full-text search also retrieves preliminary determinations, reviews, corrections, orders, and other antidumping documents.

A fixed, case-insensitive title expression then required `Final Affirmative Determination` or `Final Affirmative Determinations` followed by `of Sales at Less[- ]Than[- ]Fair[- ]Value`. Titles containing `Correction`, `Amended`, `Court Decision`, `Circumvention`, `Preliminary`, `Administrative Review`, or `Order` were excluded. This leaves 96 documents:

| Year | Strict-family documents |
|---|---:|
| 2021 | 61 |
| 2022 | 24 |
| 2023 | 11 |
| **Total** | **96** |

The 96 records occur on only 43 unique publication dates. The sorted metadata inventory has SHA-256 `8998fe3d8c60c3bb068fe6230a747010ed8b65a13e253e9e523212d4911fe677`. Two additional regex matches were correction/amendment-family records and were excluded, producing 98 pre-exclusion matches.

This program requires a genuinely high-frequency homogeneous announcement family before obtaining PDFs or inspecting legal-entity coverage. The prespecified source-design screen is at least 100 documents in total and at least 20 in every training year. The family fails both the total threshold (96) and the 2023 threshold (11). Exact investigated exporter/producer extraction, correction handling, frozen-issuer equality, and trading-calendar availability can only reduce coverage. No CVD notice, preliminary determination, review, scope ruling, order, or later correction was added after observing the shortfall.

Final state: `source_publication_semantics_feasible=true`, `economic_family_feasible=false`, `preregistered=false`, `api_corpus_persisted=false`, `training_pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.

