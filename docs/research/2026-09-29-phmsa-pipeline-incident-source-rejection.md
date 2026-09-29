# PHMSA pipeline incident reports source rejection

Decision: **ABANDON_PHMSA_PIPELINE_INCIDENT_SOURCE**. The proposed 2021–2023 Pipeline and Hazardous Materials Safety Administration pipeline-incident line is frozen at the public-availability and historical-vintage source gates, before preregistration, incident-file acquisition, operator matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Regulatory report dates do not establish public availability

PHMSA requires operators to submit incident or accident reports within 30 days under 49 CFR Parts 191 and 195. The public incident files contain incident times, locations, operator information, consequences, released commodity, causes, and other report fields. This reporting deadline establishes an operator-to-regulator obligation, not the date or time that PHMSA first placed an individual report in the public download.

The official incident-data pages expose current cumulative ZIP files for gas distribution, gas transmission and gathering, hazardous liquids, LNG, and newer gathering categories. They do not document a per-record first-publication timestamp. Incident occurrence date, operator preparation or submission date, PHMSA receipt date, and the 30-day filing deadline therefore cannot be substituted for actual public availability.

Official references:

- PHMSA pipeline incident/accident data: https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data
- PHMSA source-data overview: https://www.phmsa.dot.gov/data-and-statistics/pipeline/source-data
- PHMSA pipeline incident 20-year trends: https://www.phmsa.dot.gov/data-and-statistics/pipeline/pipeline-incident-20-year-trends
- PHMSA pipeline incident flagged files: https://www.phmsa.dot.gov/data-and-statistics/pipeline/pipeline-incident-flagged-files
- Hazardous-liquid incident-report instructions: https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/2023-06/HL_Accident_Instructions_PHMSA%20F%207000-1_2021-03%20thru%202023-04.pdf

## Supplemental reports mutate the current record

PHMSA's instructions distinguish original, supplemental, and final reports. Operators must file multiple supplemental reports when new, updated, or corrected information becomes available. Even an original-plus-final or supplemental-plus-final report can be followed by another supplemental report. Online supplemental forms are populated from previously submitted data and then edited.

The current downloadable files and trend products combine the latest report information and PHMSA-derived flags. The official materials reviewed do not expose immutable monthly vintages for all 2021–2023 downloads, the first public bytes of each report, or a complete field-level ledger of every original, supplemental, final, corrected, and replaced state. A stable report number and a current report-type field therefore do not reconstruct what the public could observe on a historical trading date.

No economically homogeneous system/severity family was counted and no operator mapping was attempted because the point-in-time source failed first. Any viable design would have had to freeze one pipeline system and one incident-severity definition before observation, without combining gas distribution, gas transmission, gathering, hazardous liquids, LNG, changing reporting criteria, or derived trend flags. Exact matching would have allowed only a full operator legal name equal to a frozen SEC issuer name; facility or system names, OPIDs, subsidiaries, parents, brands, former names, addresses, abbreviations, fuzzy matching, and manual aliases were forbidden.

The line must not be reopened by using occurrence date, report submission or receipt date, the 30-day deadline, today's current ZIP, current report type, or current trend flags as a public timestamp; by assuming a final report cannot later change; by deleting amended cases after observing them; or by mixing system types and severity definitions to increase coverage.

Final state: `public_availability_semantics_passed=false`, `historical_vintage_gate_passed=false`, `preregistered=false`, `incident_files_acquired=false`, `event_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
