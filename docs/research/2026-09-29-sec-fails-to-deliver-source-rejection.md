# SEC fails-to-deliver source rejection

Decision: **ABANDON_SEC_FTD_PUBLIC_AVAILABILITY_GATE**. The proposed 2021-2023 SEC Fails-to-Deliver Data line is frozen at the public-availability and historical-version gates, before file acquisition, event construction, exact-symbol coverage measurement, event-cube access, or any post-availability return read. This settlement-failure source is distinct from SEC issuer filings, administrative proceedings, trading suspensions, and FINRA short-volume flow. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official source audit

The official SEC archive is structurally complete at the semi-month level and documents the raw fields `SETTLEMENT DATE`, `CUSIP`, `SYMBOL`, `QUANTITY (FAILS)`, `DESCRIPTION`, and prior-day `PRICE`. Starting July 2009, each month is split into two files. The SEC says the first half is available at the end of the month and the second half at about the 15th of the next month.

That schedule is not an auditable event timestamp. The same official page explicitly says the SEC cannot guarantee that the data will be posted by a particular date and cannot guarantee accuracy. It provides no per-file first-publication timestamp, immutable release manifest, original-object hash, or complete correction/replacement ledger for the 72 semi-monthly 2021-2023 objects. Current URLs and current HTTP metadata cannot establish when each historical file first became public or whether its current bytes equal the first-published bytes. Applying a fixed month-end or next-month-15th lag would therefore invent availability and can leak a file that was actually posted later.

Official sources:

- https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data
- https://www.sec.gov/about/webmaster-frequently-asked-questions
- https://www.sec.gov/data-research/sec-data-resources

No self-normalized event threshold was preregistered because source availability failed first. The file warning also remains binding: fails can arise from long or short sales and are not evidence of abusive or naked short selling. A future design may not relabel FTD quantity as directional short conviction without independent causal support.

Final state: `public_availability_gate_passed=false`, `historical_version_gate_passed=false`, `preregistered=false`, `semi_monthly_files_acquired=false`, `event_construction_frozen=false`, `point_in_time_symbol_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. Do not reopen with assumed month-end/15th publication, current Last-Modified headers, current archive bytes, current or guessed symbol histories, share-class folding, issuer/parent/subsidiary relations, former names, abbreviations, fuzzy matches, or manual aliases. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
