# Local fallback memory: MSHA accident, injury, and illness data

summary: MSHA accident, injury, and illness data were rejected at the public-availability and historical-vintage gates. The Open Government file uses document number as a unique key and is normally updated Friday afternoons, but it does not expose the specific weekly snapshot in which each 2021-2023 row first appeared. Part 50 quarterly files are refreshed about six weeks after quarter end, progress from preliminary to final, and can include records beyond the nominal closed quarter. Current cumulative files and annual final files are evolving later states; no complete immutable weekly-vintage archive, first-byte hashes, or row-level correction/deletion/reassignment ledger was found. No records were acquired, no homogeneous mine/severity family was counted, no operator was mapped, the event cube was not opened, no post-availability outcome was read, and cells_completed is zero.
stage: source_point_in_time_gate
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: failed-experiment
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source_point_in_time_gate
  - strategy:msha_accident_injury
  - status:rejected
next_step: Audit FRA 2021-2023 rail equipment accident and incident reports as a genuinely different official issuer-level transportation-safety family. First prove the relationship among event date, railroad filing date, FRA processing, monthly public-data refresh, and actual public availability; inspect stable report IDs, amendments, corrections, deletions, historical vintages, and first-publication evidence. Predeclare one homogeneous accident type and severity class, then assess exact reporting-railroad legal-name matches to frozen SEC issuers. Do not infer issuers from reporting marks, train numbers, subsidiaries, parents, brands, locations, or aliases, and do not read outcomes before a frozen coverage gate passes.
