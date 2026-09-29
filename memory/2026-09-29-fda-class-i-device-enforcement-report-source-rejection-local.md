# Local fallback memory: FDA Class I device Enforcement Reports

summary: FDA weekly Enforcement Reports for Class I medical-device recalls were rejected at the historical-release/version gate. FDA exposes weekly report dates and a selected field-change history, but the public openFDA feed is a current weekly-updated view and FDA does not provide immutable 2021-2023 weekly release bytes, a hash manifest, or every intermediate version. The full iRES API requires credentials. A metadata-only diagnostic found 849 current Class I product rows and 222 event IDs; strict complete-legal-name matching yielded only one current Class I issuer-event. No corpus was persisted, no outcome data was read, and cells_completed is zero.

stage: source-history-gate

kpi_version: versionless-fda-class-i-device-enforcement-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-history-gate, strategy:fda-class-i-device-enforcement, status:rejected, source:fda, sample:coverage-limited-527

next_step: Audit NHTSA Office of Defects Investigation 2021-2023 formal investigation-opening resumes as a distinct non-recall family. First prove the public posting timestamp, stable investigation and document IDs, immutable opening-resume bytes, and amendment/upgrade/closing chain. Then measure one predeclared investigation type and exact manufacturer legal-name overlap without using brands, vehicle models, subsidiaries, parents, former names, abbreviations, or aliases. Do not read outcomes before a frozen metadata-only coverage gate passes.

## Frozen evidence

FDA documentation distinguishes Weekly Enforcement Report Date, Center Classification Date, and later posted changes. The history feature covers Classification, Reason for Recall, Code Information, and Product Description from July 24, 2018, but it is not a full immutable report-byte archive. Current openFDA rows cannot be backdated to reconstruct first-public Class I state. The official current API diagnostic returned 849 Class I product rows, 222 event IDs, and 131 firm strings for classification dates in 2021-2023; events by year were 74/66/82. The all-class current-corpus diagnostic contained 6,955 rows and only 50 strict full-name issuer-event overlaps across 10 frozen issuers; the Class I subset had one exact overlap, Penumbra Inc. Apparent suffix-stripped parent/subsidiary matches were explicitly rejected. `ABANDON_FDA_CLASS_I_DEVICE_ENFORCEMENT_HISTORY_GATE`; `cells_completed=0`; `post_availability_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
