# FDA Class I device Enforcement Report source rejection

Decision: **ABANDON_FDA_CLASS_I_DEVICE_ENFORCEMENT_HISTORY_GATE**. The proposed 2021-2023 FDA weekly Enforcement Report line is frozen at the historical-release/version gate. No weekly corpus or report bytes were persisted, the frozen event cube was not opened for outcomes, and no post-availability return was read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official publication contract

FDA's official documentation establishes useful but insufficient point-in-time metadata:

- The weekly Enforcement Report contains recalls after classification and can also contain recalls whose classification is still pending.
- `report_date` / `enforcementreportdt` is the Weekly Enforcement Report date.
- `center_classification_date` is the Center Classification Date, not proof of the time at which the Class I value first became public.
- The history feature marks changes to Classification, Reason for Recall, Code Information, and Product Description for recalls posted or updated since July 24, 2018. The current detail page still displays current data, while the history view records selected field changes.
- `eventlmd` is the date on which a new value was posted, and `firmlegalnam` is the original recalling-firm name at the time of recall.

Official sources:

- https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/enforcement-reports
- https://www.fda.gov/safety/enforcement-reports/enforcement-report-information-and-definitions
- https://www.fda.gov/safety/enforcement-reports/enforcement-report-history-feature
- https://www.fda.gov/safety/enforcement-reports/enforcement-report-api-definitions
- https://www.accessdata.fda.gov/scripts/ires/apidocs/
- https://open.fda.gov/apis/device/enforcement/

The public openFDA dataset is a weekly updated **current** view. FDA does not publish an immutable byte snapshot or hash manifest for each 2021-2023 weekly report, and the documented history is a selected field-change log rather than a complete first-release and intermediate-version byte archive. The full iRES API also requires an authorization user and key. Therefore neither `report_date`, `center_classification_date`, the current openFDA row, nor the current dynamic weekly-report page can prove the complete first-public Class I state and bytes for every historical event. A Class I value assigned or changed after the first weekly listing makes this distinction causal rather than cosmetic.

## Metadata-only structural diagnostic

Before any outcome access, the official current openFDA API was queried only for source-volume and entity-structure diagnostics. The fixed query for current Class I device records with Center Classification Date in 2021-2023 returned 849 product rows, 222 unique `event_id` values, and 131 recalling-firm strings. Unique events by classification year were 74, 66, and 82.

A deliberately broader all-class query over the same classification-date interval returned 6,955 current device rows. It was used as a conservative current-corpus ceiling for exact-name overlap, not as an admissible historical event inventory. After deduplicating to `event_id`, retaining the legal suffix, and allowing only Unicode/case/punctuation/whitespace normalization, exact equality between `recalling_firm` and the frozen SEC issuer title produced only 50 issuer-event pairs across 10 issuers. The year counts were 14/21/15 pairs and 7/6/6 issuers. Within the current Class I subset, only `Penumbra Inc.` matched, for one issuer-event in 2021.

This diagnostic does not rescue the failed version gate. It also shows that dropping legal suffixes would be invalid: apparent matches such as `Medtronic Inc` to `Medtronic plc`, `ResMed Ltd.` to `RESMED INC`, or `Boston Scientific Corporation` to `BOSTON SCIENTIFIC CORP` are different complete legal names and are rejected under the frozen no-subsidiary/no-parent rule. Product names, trade names, manufacturers other than the recalling firm, addresses, brands, former names, abbreviations, and manual aliases remain forbidden.

Final state: `historical_release_bytes_auditable=false`, `complete_version_manifest_available=false`, `preregistered=false`, `weekly_corpus_persisted=false`, `strict_metadata_mapping_diagnostic_performed=true`, `event_cube_opened_for_outcomes=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. Do not reopen this line with current rows, fixed publication lags, the first report date, classification date, selected history fields, legal-suffix deletion, or mixed device/drug/food/veterinary/Class II/Class III records. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.

