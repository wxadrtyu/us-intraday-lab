---
type: failed-experiment
summary: The preregistered Federal Register DOJ consent-decree screen reproduced 255 unique documents (96/81/78 for 2021/2022/2023) and acquired all 255 official GovInfo PDFs with zero failures. A deterministic deliberately permissive upper-bound scan across the entire current SEC universe found only 38 issuers and 94 symbol-document pairs, below the frozen 50/200 coverage floors; family and family-year floors also failed. Because the frozen 527 sample is a subset and strict defendant mapping can only reduce these counts, the line is frozen before event-cube access or return loading.
stage: coverage-gate
kpi_version: federal-register-consent-decree-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:coverage-gate
  - strategy:federal-register-consent-decree
  - status:rejected
next_step: Preserve the API, official PDF, SEC-source, parser, and upper-bound manifest hashes. Do not relax entity mapping or family gates. Audit a genuinely different free official dated-document family with provable release/version semantics and enough exact public-company respondents before any preregistration or outcome access.
---

Decision is `ABANDON_FEDERAL_REGISTER_CONSENT_DECREE_COVERAGE_GATE`; `source_complete=true`, `training_pdf_inventory_acquired=true`, `frozen_527_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, and `post_availability_outcomes_loaded=false`.

Evidence hashes: Federal Register API `e5d73a4c3d265448a9f43d3d430319fa973cf95f9d4b15ab41287b5ce1b6bb34`; current SEC source `affa8f025ab31bab39b60e06cf0bcc401bb87f23151412d686258fc9b99ef091`; PDF manifest `f8f726d140fa5688ce0d5b8e649b72c9c9e16e4fd6748e0a04fc78b70a5e3d04`; deterministic party-role upper bound `90b871380d0f1aa8f9e5e25f9c6d649875291e5731bfe3c5fa0552429966ac93`. The 255 official PDFs total 51,923,632 bytes and have 255 distinct hashes. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
