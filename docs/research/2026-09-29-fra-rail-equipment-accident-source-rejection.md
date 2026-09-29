# FRA rail equipment accident data source rejection

Decision: **ABANDON_FRA_RAIL_EQUIPMENT_ACCIDENT_SOURCE**. The proposed 2021–2023 Federal Railroad Administration rail equipment accident/incident line is frozen at the public-availability and historical-vintage source gates, before preregistration, dataset acquisition, railroad matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Monthly regulatory reporting is not a public release timestamp

FRA requires railroads to submit monthly accident/incident reports. Form F 6180.54 covers reportable collisions, derailments, fires, explosions, and other on-track equipment events above the applicable monetary threshold. FRA's public safety-data site exposes current accident/incident reports and annual downloadable files.

The railroad's event date, internal record date, report month, completion date, electronic submission date, and regulatory deadline do not establish when FRA first added a particular row to the public database. The public download and query pages state the latest month through which the database is current, but do not expose a per-record first-publication date or timestamp for 2021–2023.

Official references:

- FRA safety data portal: https://railroads.dot.gov/safety-data
- FRA accident/incident reporting requirements: https://railroads.dot.gov/forms-guides-publications/forms/accidentincident-recordkeeping-and-reporting-requirements
- FRA accident/incident definitions: https://railroads.dot.gov/forms-guides-publications/guides/accidentincident-definitions
- FRA current accident/incident query: https://safetydata.fra.dot.gov/OfficeofSafety/publicsite/query/QueryOverview.aspx
- FRA downloadable database description: https://safetydata.fra.dot.gov/OfficeofSafety/publicsite/Aboutdbf.htm
- FRA Guide for Preparing Accident/Incident Reports: https://safetydata.fra.dot.gov/PublicObjects/FRAGuideforPreparingAccIncReportspubMay2011.pdf

## Current files incorporate late reports and amendments

FRA's reporting system accepts late and amended reports. The reporting guide requires a railroad to replace an initially undetermined cause with an amended report after its investigation progresses, and permits cause-code amendments for years after the event. FRA's electronic-submission materials describe update and maintenance of year-to-date data. The query site produces current, dynamic outputs and says all outputs are generated at the current top level of railroad consolidation, regardless of the requested historical period.

The annual download labeled for a past year is therefore a current consolidated representation, not necessarily the bytes or entity hierarchy first made public during that year. The official materials reviewed do not provide immutable monthly vintages for every 2021–2023 release, first-publication hashes, or a complete record-level ledger of late additions, amendments, corrections, deletions, and consolidation changes. Current reporting marks and current top-level railroad ownership would also introduce hindsight into issuer mapping.

No economically homogeneous accident type and severity class was counted and no railroad mapping was attempted because the point-in-time source failed first. Any viable design would have had to freeze one Form F 6180.54 event class and severity rule before observation, without mixing train accidents, highway-rail incidents, employee casualties, fatal and nonfatal cases, inspections, or enforcement. Exact matching would have allowed only the full reporting-railroad legal name as first published equal to a frozen SEC issuer name; reporting marks, train numbers, subsidiaries, parents, brands, locations, former names, abbreviations, fuzzy matching, and manual aliases were forbidden.

The line must not be reopened by using event date, report month, submission date, a database-current-through month, today's annual download, today's dynamic query, or current consolidation as the historical public state; by discarding late or amended reports after observing them; or by mixing report forms, accident types, and severity classes to increase coverage.

Final state: `public_availability_semantics_passed=false`, `historical_vintage_gate_passed=false`, `preregistered=false`, `datasets_acquired=false`, `event_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
