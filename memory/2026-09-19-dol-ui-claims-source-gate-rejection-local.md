---
type: failed-experiment
summary: Official DOL UI-claims 2021-2023 source archive is complete and hashed, but strict first-page-only parsing is 153/156; source gate fails before any return outcome read or 400-cell diagnostic.
stage: source-coverage-gate
kpi_version: dol-ui-claims-training-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-coverage-gate
  - strategy:dol-ui-claims-training-v1
  - status:rejected
next_step: Freeze DOL evidence and preregister a genuinely different free official point-in-time causal return source; do not repair missing first pages by later-page substitution or local tuning.
---

Frozen 527-symbol training sample is coverage-limited, not full market. Exact PDF inventory and 156 raw hashes are complete. Two 2022 PDFs have split initial-claims labels in extracted first-page text; the 2023-04-06 first page is a methodology notice without the two measures. Strict source-schema completeness requires 156/156 and observed only 153/156. `ABANDON_DOL_UI_CLAIMS_COVERAGE_GATE`; `cells_completed=0`; `post_availability_outcomes_loaded=false`. Source manifest SHA `fd2f0da47c5fce9c3b4991ab1c37ea7ed156ad7fdf81fb6494ba6b8c69c9fb8b`; PDF manifest SHA `1a38d3a4d6ee868f1bb3ebf020f51508bfb01740441018e341bb228082cb4204`. MCP memory search/create unavailable; this tagged local fallback needs later MCP backfill.
