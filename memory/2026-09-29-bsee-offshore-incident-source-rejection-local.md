# Local fallback memory: BSEE offshore incident data

summary: BSEE offshore incident data were rejected at the public-availability and historical-vintage gates. Operators immediately notify BSEE of qualifying events, but that regulator notification is not a public timestamp. The current investigation-status table and annual incident spreadsheets do not expose when each event first became public. BSEE explicitly says annual totals can change based on investigation findings and events can fall into multiple categories. Panel and selected district reports may have publication dates and PDFs, but they are a delayed selected subset and cannot be mixed with the full incident feed. No complete immutable 2021-2023 data-center snapshots, row first-publication hashes, or classification/status revision ledger was found. No data were acquired, no homogeneous class was counted, no operator was mapped, the event cube was not opened, no post-availability outcome was read, and cells_completed is zero.
stage: source_point_in_time_gate
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: failed-experiment
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source_point_in_time_gate
  - strategy:bsee_offshore_incidents
  - status:rejected
next_step: Audit U.S. Coast Guard 2021-2023 Port State Control detention publications as a genuinely different official issuer-level maritime enforcement family. First prove monthly or case-level publication timing, index completeness, stable detention identifiers, corrections or removals, historical immutable releases, and first-publication bytes. Predeclare one homogeneous detention ground or enforcement class, then assess exact owner or operator legal-name matches to frozen SEC issuers. Do not infer issuers from vessel names, IMO numbers, flags, managers, subsidiaries, parents, brands, or aliases, and do not read outcomes before a frozen coverage gate passes.
