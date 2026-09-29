# FDA 510(k) clearance source rejection

Decision: **ABANDON_FDA_510K_SOURCE**. The proposed 2021–2023 FDA traditional 510(k) substantially-equivalent clearance line is frozen at the point-in-time source gate, before preregistration, database download, applicant matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Decision date is not public availability

FDA's official 510(k) submission-process page distinguishes the regulatory decision from public database availability:

- FDA emails the decision letter to the submitter when a decision is made.
- FDA adds a cleared 510(k) to the public 510(k) database **weekly**.
- complete substantially-equivalent packages are posted **monthly**.

Therefore `Decision Date` is not the first public-web availability date. A next-sample-trading-day event keyed to that field could lead the public record by several days, while the summary package can lag further. The current database and annual browse pages do not provide a per-record first-posted timestamp that closes this gap.

Official references:

- FDA 510(k) submission process: https://www.fda.gov/medical-devices/premarket-notification-510k/510k-submission-process
- FDA 510(k) clearance overview and annual browse links: https://www.fda.gov/medical-devices/device-approvals-and-clearances/510k-clearances
- Official releasable 510(k) search: https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm
- Downloadable 510(k) files: https://www.fda.gov/medical-devices/510k-clearances/downloadable-510k-files
- Search-field description: https://www.fda.gov/medical-devices/510k-clearances/search-releasable-510k-database

## Historical-vintage and document-identity failure

FDA states that the downloadable files contain releasable records, are replaced monthly, and offer a 1996-current cumulative file plus the most-current-month file. The official page does not offer immutable monthly vintages for 2021–2023, a first-posted timestamp, a first-byte hash, or a complete replacement/correction ledger for each K-number. Annual browse pages are labelled archived, but they are clearance-date lists rather than publication-time inventories and do not prove which bytes were public on each decision date.

The database distinguishes Traditional, Special, Abbreviated, and Rescission types and exposes stable K-numbers, but stable identifiers do not repair the missing public timestamp or historical bytes. The FDA TPLC disclaimer also says the database is updated monthly and is not updated when 510(k) ownership transfers, underscoring that applicant identity and current ownership are separate concepts.

This source likely has ample gross volume, but volume cannot cure look-ahead. Applicant-name coverage was therefore not inspected. Exact matching would have allowed only the applicant legal name as recorded for that submission to equal a frozen SEC issuer name, with no device trade names, manufacturer listings, owner/operator records, transferred ownership, subsidiaries, parents, former names, abbreviations, fuzzy matching, or manual aliases.

The line must not be reopened by treating `Decision Date` as the database-posting date, imposing an observed average lag, using the current cumulative file as a historical vintage, substituting package-posting month without a per-record timestamp, or mixing De Novo, PMA, NSE, withdrawn, rescinded, special, abbreviated, or supplement actions to rescue coverage.

Final state: `public_availability_semantics_passed=false`, `historical_vintage_gate_passed=false`, `preregistered=false`, `database_downloaded=false`, `summary_inventory_acquired=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
