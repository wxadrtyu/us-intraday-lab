# Federal Register environmental consent-decree source audit

Status: **SOURCE_FEASIBLE_FOR_PREREGISTRATION**. This audit used only official publication metadata and source documentation. It did not acquire the training document corpus, map defendants, open the frozen event cube, or read any post-publication return. The 2021–2023 cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Publication time and official bytes

GovInfo identifies the Federal Register as the official daily publication and states that its online edition is the legal equivalent of paper and microfiche. The online issue is updated by 6:00 a.m. on each publication day. The issue front matter says documents are ordinarily available for public inspection on the preceding working day, but the conservative research availability rule will ignore that earlier access and use the first frozen-sample trading session strictly after the printed `publication_date`.

The Federal Register API exposes a stable `document_number`, `publication_date`, official GovInfo `pdf_url`, and separate public-inspection URL. Only the GovInfo publication PDF is admissible source content. GovInfo provides issue and granule packages, PDF/XML/text renditions, and preservation metadata including fixity actions. A later FederalRegister.gov HTML rendition, excerpt, public-inspection draft, DOJ consent-decree library copy, or search-result snippet may help locate a record but may not replace the official published PDF.

## Gross event-volume audit

The exact source-screen query was Department of Justice (`justice-department`), publication dates 2021-01-01 through 2023-12-31, and search term `consent decree`. Restricting returned records to titles containing `Consent Decree` produced 255 unique document numbers: 96 in 2021, 81 in 2022, and 78 in 2023. Prominent title groups included 47 Clean Air Act notices, 29 Clean Water Act notices, two CERCLA title variants with 33 and 15 notices, and smaller RCRA, OPA, TSCA, amendment, modification, correction, and multi-statute groups.

This count is only a structural upper inventory. It includes amendments, modifications, extensions, corrections, private or municipal defendants, and records whose full caption may not state a frozen SEC issuer title. It therefore does not establish usable coverage, but it is large enough to justify a preregistered metadata-only exact-name audit rather than a design-stage rejection.

Final state: `source_feasible=true`, `preregistered=false`, `training_pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
