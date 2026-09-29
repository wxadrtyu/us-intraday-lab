# Local fallback memory: NTSB aviation preliminary reports

summary: NTSB aviation preliminary reports were rejected at the historical-version gate. CAROL distinguishes event date from investigation publish date, and current reports can expose Original Publish Date and Last Revision Date, but the official generated-report endpoint serves the newest report. NTSB notes that reports may be corrected and republished, preliminary reports are subject to change, published searches are dynamic, and the downloadable aviation dataset is updated monthly. No official immutable archive, hash manifest, or retrieval path for every first and intermediate preliminary-report version was found. Current PDF and CAROL fields therefore cannot reconstruct the exact 2021-2023 public information set. No corpus was acquired, no homogeneous family was counted, no operator was mapped, the event cube was not opened, no post-availability outcome was read, and cells_completed is zero.
stage: source_historical_version_gate
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: failed-experiment
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source_historical_version_gate
  - strategy:ntsb_aviation_preliminary_reports
  - status:rejected
next_step: Audit PHMSA 2021-2023 pipeline incident reports as a genuinely different official issuer-level event family. First prove the relationship among occurrence date, operator submission date, report receipt date, monthly public-data refresh, and actual public availability; inspect stable report IDs, original/final/supplemental filings, corrections, replacement history, and preservation of first-publication bytes. Predeclare one homogeneous pipeline-system and incident-severity family, then assess exact operator legal-name matches to frozen SEC issuers. Do not infer issuers from facilities, pipeline systems, subsidiaries, parents, brands, or aliases, and do not read outcomes before a frozen coverage gate passes.
