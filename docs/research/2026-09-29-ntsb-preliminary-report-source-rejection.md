# NTSB aviation preliminary reports source rejection

Decision: **ABANDON_NTSB_AVIATION_PRELIMINARY_REPORT_SOURCE**. The proposed 2021–2023 National Transportation Safety Board aviation preliminary-report line is frozen at the historical-version source gate, before preregistration, corpus acquisition, operator matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Publication metadata are useful but the served report is the newest version

NTSB's CAROL search exposes investigation event-date and investigation publish-date filters, and its guide defines `Original published date` as the date an investigation report was originally published. The guide also explicitly notes that investigation reports are sometimes corrected and republished. Generated aviation reports can display both `Original Publish Date` and `Last Revision Date`.

This is sufficient to distinguish accident occurrence from report publication, but not to recover the information actually contained in the first public preliminary report. The official report endpoint is named `GenerateNewestReport`, and current preliminary reports state that their information is preliminary and subject to change. NTSB's public guidance does not expose immutable identifiers or hashes for every historical preliminary-report version, a manifest of replacements, or an endpoint for retrieving the exact bytes initially served on the original publication date.

Official references:

- NTSB accident-data resources: https://www.ntsb.gov/safety/data/Pages/Data_Stats.aspx
- NTSB CAROL help: https://www.ntsb.gov/Pages/CAROL.aspx
- NTSB CAROL guide: https://www.ntsb.gov/Documents/CAROL-Guide.pdf
- NTSB basic search with event- and publish-date fields: https://my.ntsb.gov/basic
- Example current preliminary report generated through `GenerateNewestReport`: https://data.ntsb.gov/carol-repgen/api/Aviation/ReportMain/GenerateNewestReport/193533/pdf
- Example current final report showing original and revision dates: https://data.ntsb.gov/carol-repgen/api/Aviation/ReportMain/GenerateNewestReport/68790/pdf

## Current downloads cannot reconstruct the 2021–2023 public information set

CAROL's published searches are documented as dynamic queries that reflect current database information each time they are opened. The downloadable 1982-to-present aviation dataset is updated monthly, while CAROL's current CSV and JSON exports return current query records. The July 2023 CAROL relaunch also changed and expanded the downloadable data. These facilities are useful current indexes, not immutable daily or per-publication snapshots.

An original publication date plus a current `Last Revision Date` identifies that change occurred, but does not reveal all intermediate states or restore the initial bytes. The current generated preliminary report and current CAROL fields therefore cannot support a point-in-time 2021–2023 operator/event mapping without importing later edits. Accident date, docket creation date, final-report date, current PDF headers, and current HTTP metadata cannot substitute for the missing historical version.

No economically homogeneous accident or incident class was counted and no operator mapping was attempted because the version gate failed first. Any viable design would have had to freeze one severity and one operating category before observation, excluding final reports, recommendations, later investigative updates, and other modes. Exact matching would have allowed only the full operator legal entity printed in the contemporaneous preliminary report equal to a frozen SEC issuer name; flight numbers, registrations, aircraft manufacturers, brands, subsidiaries, parents, former names, abbreviations, fuzzy matching, and manual aliases were forbidden.

The line must not be reopened by treating occurrence date, current CAROL `Original Publish Date`, docket dates, the current `GenerateNewestReport` PDF, today's monthly database, or today's dynamic query as the first-publication record; by excluding revised cases after observing them; or by mixing accident severity, operating categories, reports, and recommendations to increase coverage.

Final state: `publication_metadata_available=true`, `historical_version_gate_passed=false`, `preregistered=false`, `corpus_acquired=false`, `event_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
