# OSHA Severe Injury Reports source rejection

Decision: **ABANDON_OSHA_SEVERE_INJURY_SOURCE**. The proposed 2021–2023 OSHA Severe Injury Reports line is frozen at the point-in-time source gate, before preregistration, data download, employer matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Report time is not public availability

OSHA requires employers under federal jurisdiction to report a work-related in-patient hospitalization, amputation, or loss of an eye within 24 hours. That obligation establishes when OSHA may receive a report; it does not establish when the public could retrieve the row. OSHA's official Severe Injury Reports page says only that the public reports “will be updated periodically.” The current dashboard likewise says the data are updated periodically and gives a moving coverage-through date, not a per-row first-published timestamp.

The current dashboard was launched on September 4, 2024 and retroactively includes reports from 2015 onward. An older official download page existed and exposed a cumulative file with a coverage-through date, but the current official source does not provide an immutable inventory of each 2021–2023 release, its publication timestamp, its hash, or the rows contained in each release. `Event Date` and the statutory 24-hour reporting deadline therefore cannot be used as public availability.

Official references:

- OSHA Severe Injury Reports page: https://www.osha.gov/severeinjury
- OSHA Severe Injury Dashboard: https://www.osha.gov/severe-injury-reports
- OSHA dashboard launch release, September 4, 2024: https://www.osha.gov/news/newsreleases/trade/20240904
- Legacy official cumulative-download page: https://obis.osha.gov/severeinjury/index.html
- OSHA recordkeeping update explaining the reporting deadline: https://www.osha.gov/sites/default/files/publications/OSHA3745.pdf

## Historical-vintage and identity failure

The available official pages describe a periodically or regularly updated cumulative dataset. They do not expose a 2021–2023 sequence of immutable vintages, a first-publication timestamp for each report, a complete correction/deletion/duplicate ledger, or superseded bytes. Freezing today's cumulative object would preserve only today's representation, not the public information set on a historical event date.

The reported name is also the **establishment where the incident happened**, not a guaranteed SEC-issuer legal name. Exact matching would have allowed only a mechanically equal legal employer name known in the report to equal a frozen issuer name. Addresses, NAICS, establishment or site names, brands, subsidiaries, parents, former names, abbreviations, fuzzy matching, and manual aliases were forbidden. No mapping was attempted because the point-in-time gate failed first.

The line must not be reopened by assuming immediate publication after the 24-hour report deadline, applying a guessed periodic-release lag, using the current cumulative file as a historical vintage, relying on a dashboard coverage-through date as a row timestamp, or mixing hospitalizations, amputations, eye losses, fatalities, inspections, citations, or news releases to rescue coverage.

Final state: `public_availability_semantics_passed=false`, `historical_vintage_gate_passed=false`, `preregistered=false`, `dataset_downloaded=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
