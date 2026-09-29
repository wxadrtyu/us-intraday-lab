# Local fallback memory: FRA rail equipment accident data

summary: FRA rail equipment accident data were rejected at the public-availability and historical-vintage gates. Railroads submit monthly Form F 6180.54 reports, but event, record, report-month, completion, submission, and regulatory due dates do not establish when a row first became public. FRA's query and annual downloads expose current data through a stated month. Late and amended reports can update accident causes years later, and historical queries are generated at the current top level of railroad consolidation. No per-record first-publication timestamp, complete immutable 2021-2023 monthly-vintage archive, first-byte hashes, or full amendment/deletion/consolidation ledger was found. No datasets were acquired, no homogeneous class was counted, no railroad was mapped, the event cube was not opened, no post-availability outcome was read, and cells_completed is zero.
stage: source_point_in_time_gate
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: failed-experiment
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source_point_in_time_gate
  - strategy:fra_rail_equipment_accidents
  - status:rejected
next_step: Audit BSEE 2021-2023 offshore incident data and formal incident-investigation publications as a genuinely different official issuer-level safety family. First prove the relationship among occurrence, operator notification or filing, BSEE processing, public data refresh or report publication, and actual public availability; inspect stable incident IDs, revisions, corrections, historical vintages, and first-publication bytes. Predeclare one homogeneous offshore incident class and severity rule, then assess exact operator legal-name matches to frozen SEC issuers. Do not infer issuers from leases, facilities, platforms, operator numbers, subsidiaries, parents, brands, or aliases, and do not read outcomes before a frozen coverage gate passes.
