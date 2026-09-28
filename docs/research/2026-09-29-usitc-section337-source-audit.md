# USITC Section 337 institution-notice source audit

Status: **SOURCE_FEASIBLE_FOR_COVERAGE_PREREGISTRATION**. This audit used official publication metadata and official USITC structural statistics only. It did not acquire the GovInfo training PDF corpus, map respondents, open the frozen event cube, or read any post-publication return. The 2021-2023 cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Public-time and version semantics

The admissible event is only an International Trade Commission **institution notice published in the Federal Register**. The same official Federal Register/GovInfo contract already audited for this repository applies: `publication_date` is the official issue date, GovInfo's online Federal Register is the legal equivalent of the printed edition and is updated by 6:00 a.m. on publication day, and each API record supplies a stable document number and official GovInfo PDF URL. Research availability is conservatively the first frozen-sample trading session strictly after `publication_date`; earlier public-inspection access is ignored.

Only the official GovInfo publication PDF is admissible content. A correction or later Commission notice is a separate event record and cannot rewrite the published PDF. FederalRegister.gov HTML/text/XML, public-inspection drafts, USITC news releases, EDIS copies, search snippets, and later merits or termination notices cannot substitute for the official institution-notice PDF.

## Exact structural inventory

The fixed Federal Register API screen uses agency slug `international-trade-commission`, publication dates 2021-01-01 through 2023-12-31, search phrase `"Institution of Investigation"`, oldest-first order, and `per_page=1000`. It returns 148 records on one page. Because the API term search is full-text, the frozen case-insensitive title literal `INSTITUTION OF INVESTIGATION` excludes three documented false positives (`2021-09991`, `2022-16049`, and the termination notice `2022-20575`) and retains 145 unique notices: 50/60/35 by Federal Register publication year 2021/2022/2023. A detail probe confirms that records expose `document_number`, `publication_date`, GovInfo `pdf_url`, `raw_text_url`, `full_text_xml_url`, and corrections metadata.

The official USITC calendar-year statistics independently report 52, 59, and 37 Section 337 investigations in 2021, 2022, and 2023, totaling 148. The source inventory has 145 institution-notice documents, and the annual splits need not coincide because one series uses investigation institution dates while the source inventory uses Federal Register publication dates and document notices. The acquisition stage must account for every API record, title exclusion, duplicate, correction, URL identity, and PDF failure.

The external source-audit manifest SHA-256 is `5591ee0820267d5d34b76e97f1d585469f0e70da313572dd5795f12967fbe930`; the raw API response SHA-256 is `0c860f90ac91dd39862b5e7990e14025a10110a0e270bfed9e60581b78f44f32`.

Final state: `source_feasible=true`, `coverage_preregistered_separately=true`, `training_pdf_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
