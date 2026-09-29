# Local fallback memory: PHMSA pipeline incident reports

summary: PHMSA pipeline incident reports were rejected at the public-availability and historical-vintage gates. Operators must report qualifying incidents within 30 days, but occurrence, submission, receipt, and regulatory due dates do not establish when a record first entered the public download. PHMSA publishes current cumulative system-specific files. Original, supplemental, and final reports can repeatedly add, update, or correct fields, including after a report was marked final. No per-record first-publication timestamp, complete immutable 2021-2023 monthly-vintage archive, first-byte hashes, or field-level revision ledger was found. No incident files were acquired, no homogeneous system/severity family was counted, no operator was mapped, the event cube was not opened, no post-availability outcome was read, and cells_completed is zero.
stage: source_point_in_time_gate
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: failed-experiment
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source_point_in_time_gate
  - strategy:phmsa_pipeline_incidents
  - status:rejected
next_step: Audit MSHA 2021-2023 mine accident, injury, and illness data as a genuinely different official issuer-level workplace-safety family. First prove the relationship among accident date, operator filing date, MSHA processing, quarterly or periodic data publication, and actual public availability; inspect stable case IDs, current cumulative downloads, corrections/deletions, historical vintages, and first-publication evidence. Predeclare one homogeneous injury or accident class and mine type, then assess exact operator legal-name matches to frozen SEC issuers. Do not infer issuers from mine names, controller IDs, subsidiaries, parents, brands, addresses, or aliases, and do not read outcomes before a frozen coverage gate passes.
