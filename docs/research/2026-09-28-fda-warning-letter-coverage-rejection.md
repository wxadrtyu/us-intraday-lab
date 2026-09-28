# FDA Warning Letter coverage-gate rejection

Decision: **ABANDON_FDA_WARNING_LETTER_COVERAGE_GATE**. The line is frozen after acquiring the exact preregistered official index page and standard XLSX export, but before issuer mapping, event-cube access, or any post-availability return read. The frozen 2021–2023 event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Immutable source evidence

- Official index URL: `https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters`
- Index bytes: `76,449`
- Index SHA-256: `6671da67aa6712ab057ccc982d001bdf772e9d2a2459db1b3f09618ccd9f14b6`
- Index-declared `total_items`: `3,701`
- Preregistered standard XLSX URL: `https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/warning-letters/datatables-data?_format=xlsx&page=`
- XLSX bytes: `52,637`
- XLSX SHA-256: `7fc4481d2c37c2ed012718601f648d0f9b9fdc9b41d62257cec0f198c7635c7d`
- Workbook sheet: `Warning Letter Solr Index`
- Workbook rows: `1,000`
- External manifest SHA-256: `26891bb5772b1aa0adcb5b951e6341b448de7a41fc3ef34bb390f8e7c9d8ae24`

The downloaded workbook has the seven expected columns, no missing company, subject, posted-date, or issue-date values, and no posted-before-issue record. Its posted dates span 2021-01-05 through 2026-04-28. It contains only 647 training-date rows: 94 in 2021, 548 in 2022, and 5 in 2023.

## Gate decision

The preregistration requires one complete, hash-frozen official XLSX response before any mapping or outcomes. The standard export contains 1,000 rows while the same official index declares 3,701 items, leaving a 2,701-row shortfall. It is therefore not the complete archive required by the frozen contract.

The index also advertises a separate batch-export URL. That endpoint was not the preregistered source. Fetching it after observing the standard-export truncation would change the exact source and acquisition contract after inspection. It is not used to rescue this line. No pagination, batch substitution, threshold relaxation, issuer alias, or partial-year inference is permitted.

Final state: `source_complete=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
