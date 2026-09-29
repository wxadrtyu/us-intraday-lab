# NRC Event Notification Reports source rejection

Decision: **ABANDON_NRC_EVENT_NOTIFICATION_SOURCE**. The proposed 2021–2023 U.S. Nuclear Regulatory Commission Event Notification Reports line is frozen at the historical-version source gate, before preregistration, daily-report acquisition, licensee matching, event-cube access, or any post-availability return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Promising daily publication structure

NRC provides official yearly indexes of dated daily Event Notification Reports. Each report carries event numbers, notification and event timestamps, event type, applicable 10 CFR sections, facility or licensee information, and event text. This is materially stronger publication evidence than a current cumulative database: the archive exposes a stable URL for each report date and the report date can conservatively define a public daily boundary.

Official references:

- NRC Event Notification Reports collection: https://www.nrc.gov/documents-reports/document-collections/events-reports-associated-with/event-notification-reports
- 2021 daily-report index: https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2021/index
- 2023 daily-report index: https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2023/index
- Example September 9, 2023 report: https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2023/20230909en
- Example August 29, 2021 report containing later revisions: https://www.nrc.gov/reading-rm/doc-collections/event-status/event/2021/20210829en

## Current daily pages are later revised representations

The dated URL is not an immutable first-publication object. The current August 29, 2021 page says Event 55435 had a `Last Update Date` of September 1 and an `EN Revision Imported Date` of September 30. On the same page, Event 55436 has an October 25 update, a November 24 revision-import date, and a partial retraction. Thus a page identified by an August 29 URL can contain information added weeks or months later.

The displayed update markers are useful, and some pages appear to preserve initial narrative followed by timestamped updates. However, the official collection does not state that revisions are always append-only, guarantee that initial bytes and every intermediate version are retained, expose immutable first-release hashes, or provide a complete version manifest. Parsing today's page and truncating at the first visible `UPDATE` would therefore rely on an unproven preservation convention. Current bytes cannot be asserted to equal the public information set on the daily report date.

No economically homogeneous event family was counted and no licensee mapping was attempted because the version gate failed first. A later viable design would have required one fixed report type and one fixed 10 CFR trigger, not a post-observation mixture of reactor and non-reactor events, unusual events, shutdowns, medical events, security events, corrections, retractions, or updates. Exact matching would have allowed only a full licensee legal name equal to a frozen SEC issuer name; facility or unit names, operators, dockets, addresses, subsidiaries, parents, former names, abbreviations, fuzzy matching, and manual aliases were forbidden.

The line must not be reopened by treating `Notification Date`, `Event Date`, `Last Update Date`, a dated URL, or a current page's revision-import markers as proof of first-publication bytes; by assuming every revision is append-only; or by deleting observed retractions and corrections after the fact.

Final state: `daily_index_structure_feasible=true`, `historical_version_gate_passed=false`, `preregistered=false`, `daily_reports_acquired=false`, `event_family_counted=false`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
