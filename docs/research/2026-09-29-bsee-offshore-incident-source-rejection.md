# BSEE offshore incident data source rejection

Decision: **ABANDON_BSEE_OFFSHORE_INCIDENT_SOURCE**. The proposed 2021–2023 Bureau of Safety and Environmental Enforcement offshore-incident line is frozen at the public-availability and historical-vintage source gates, before preregistration, spreadsheet or report acquisition, operator matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Incident occurrence and notification are not public release times

BSEE requires offshore operators to notify it immediately of specified fatalities, evacuated injuries, loss of well control, fires, explosions, qualifying collisions, structural damage, crane events, and safety-system damage. BSEE publishes annual incident-statistics spreadsheets and maintains a current listing and status of formal incident investigations.

Immediate operator-to-regulator notification does not establish when an incident became public. The current investigation listing exposes occurrence date, lease, area/block, type, investigation level, and current status, and gives a data-center refresh time. It does not expose the date each incident row first appeared publicly. The annual incident-statistics page likewise gives calendar-year spreadsheets and totals without a contemporaneous, immutable release timestamp for each underlying event.

Official references:

- BSEE offshore incident statistics: https://www.bsee.gov/stats-facts/offshore-incident-statistics
- BSEE offshore incident investigations: https://www.bsee.gov/what-we-do/incident-investigations/offshore-incident-investigations
- BSEE listing and status of incident investigations: https://www.data.bsee.gov/Other/DataTables/IncidentInvestigations.aspx
- BSEE reportable incident notification and investigation policy: https://www.bsee.gov/bsee-interim-document/reportable-incident-notification-and-investigation

## Current classifications and totals change after investigation

BSEE explicitly cautions that incident totals may change annually based on investigation findings and that one incident can be counted in multiple categories. The investigation listing is a current status table updated by the Data Center. These are evolving administrative representations, not immutable historical event releases.

BSEE publishes a report at the conclusion of each panel investigation and may publish selected district investigation reports. Such reports can have a publication date and a stable PDF, but they are a selected, delayed subset whose event semantics differ from the annual incident feed. They cannot be mixed with all reported incidents to repair the missing first-publication time or increase coverage. The official materials reviewed do not provide a complete archive of every 2021–2023 daily data-center state, first-publication hashes for incident rows, or a field-level ledger of classification, status, correction, and removal changes.

No economically homogeneous incident class and severity rule was counted and no operator mapping was attempted because the point-in-time source failed first. Any viable design would have had to choose exactly one incident category and one publication channel before observation, without mixing fatalities, injuries, fires, explosions, loss of well control, spills, safety alerts, and panel or district reports. Exact matching would have allowed only a full contemporaneous operator legal name equal to a frozen SEC issuer name; leases, facilities, platforms, operator numbers, contractors, subsidiaries, parents, brands, former names, abbreviations, fuzzy matching, and manual aliases were forbidden.

The line must not be reopened by using occurrence date, immediate-notification duty, investigation approval date, current Data Center refresh time, current annual spreadsheet, or current status as historical public availability; by assuming annual totals and classifications were always the same; or by mixing annual incidents with selected investigation reports and safety alerts to increase coverage.

Final state: `public_availability_semantics_passed=false`, `historical_vintage_gate_passed=false`, `preregistered=false`, `incident_data_acquired=false`, `event_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
