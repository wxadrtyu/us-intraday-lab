# MSHA accident, injury, and illness data source rejection

Decision: **ABANDON_MSHA_ACCIDENT_INJURY_SOURCE**. The proposed 2021–2023 Mine Safety and Health Administration accident, injury, and illness line is frozen at the public-availability and historical-vintage source gates, before preregistration, record acquisition, operator matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Current weekly files do not expose row-level first publication

MSHA's Open Government portal says the Accident Injuries Data Set contains Form 7000-1 reports from mine operators and contractors, uses document number as its unique key, and is updated every Friday afternoon unless otherwise noted. The record includes accident, injury, illness, mine, lost-day, and injury-degree information.

That weekly update schedule is a useful current operating rule, but the published row fields do not establish which Friday a particular 2021–2023 document first entered the public file. Accident date, the date an operator filed Form 7000-1, MSHA processing fields, and the next nominal Friday are not interchangeable with observed public availability. Late processing, corrections, and other exceptions make a mechanically inferred Friday unproven without the corresponding historical weekly snapshot.

Official references:

- MSHA Open Government data portal: https://arlweb.msha.gov/OpenGovernmentData/OGIMSHA.asp
- MSHA Part 50 accident/injury files and production schedule: https://arlweb.msha.gov/STATS/PART50/p50y2k/AITABLE.HTM
- MSHA Part 50 data home: https://arlweb.msha.gov/STATS/PART50/p50y2k/p50y2k.HTM
- MSHA Form 7000-1 reporting instructions: https://arlweb.msha.gov/forms/70001inb.htm
- MSHA accident/injury statistics page: https://arlweb.msha.gov/accinj/accinj.htm

## The public datasets are current cumulative representations

The Open Government files are overwritten on their recurring update schedule. The Part 50 page separately describes quarterly files refreshed approximately six weeks after quarter end and labels recent releases preliminary before a later final annual release. It warns that raw files can include injuries beyond the closed-quarter date and may not match the published closed-quarter reports. MSHA also documents removal of invalid mine IDs from its master file upon discovery.

These official materials show an evolving administrative dataset, but do not provide a complete archive of every Friday snapshot, immutable hashes for the 2021–2023 weekly vintages, or a row-level ledger for initial appearance, correction, deletion, mine/operator reassignment, and duplicate resolution. Current document number uniqueness does not recover the original public fields. Final annual files are later consolidated states, not proof of what was public immediately after an accident.

No economically homogeneous injury or accident class was counted and no operator mapping was attempted because the point-in-time source failed first. Any viable design would have had to freeze one mine type, reporter type, and injury/accident classification before observation, without mixing fatal and nonfatal events, employees and contractors, coal and metal/nonmetal mines, inspections, citations, or fatalgrams. Exact matching would have allowed only a full operator legal name equal to a frozen SEC issuer name; mine names, controller IDs, subsidiaries, parents, brands, former names, addresses, abbreviations, fuzzy matching, and manual aliases were forbidden.

The line must not be reopened by using accident date, filing date, the next Friday, a quarterly refresh estimate, final annual files, or today's cumulative dataset as the first-publication time; by assuming document-number stability proves field immutability; by dropping records later corrected or removed; or by combining mine types, reporter types, severity levels, inspections, citations, and fatalgrams to increase coverage.

Final state: `weekly_schedule_documented=true`, `public_availability_semantics_passed=false`, `historical_vintage_gate_passed=false`, `preregistered=false`, `records_acquired=false`, `event_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
