# Local fallback memory: EPA Federal Register administrative settlements

summary: The EPA Federal Register administrative settlement/consent candidate was rejected at the source-volume design gate. Official publication semantics and GovInfo PDFs are point-in-time feasible, but the economically bounded CERCLA administrative settlement family has only 43 over-inclusive title matches in 2021-2023 (12/11/20); the stricter order-on-consent subset has 14 (7/2/5). This fails the fixed high-frequency screen of 100 total and 20 in each year before issuer matching. No corpus was persisted, no PDF was acquired, no issuer was mapped, the event cube was not opened, no outcome was read, and cells_completed is zero.
stage: source_design_gate
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: failed-experiment
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source_design_gate
  - strategy:epa_fr_administrative_settlement
  - status:rejected
next_step: Audit a genuinely different free official high-frequency dated-publication family. Preserve strict point-in-time bytes and exact legal-entity mapping; do not reopen this line by mixing statutes, settlement types, rules, permits, citizen suits, or aliases.
