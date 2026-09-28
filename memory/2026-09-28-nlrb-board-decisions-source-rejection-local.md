---
type: data-decision
summary: Rejected NLRB Board Decisions at the preregistration source gate. Issuance Date and E-Service semantics can support next-session availability, and official FY2021/FY2022/FY2023 reports show 243/243/246 contested-case decisions, so gross volume is not the immediate blocker. The official index explicitly says slip opinions are subject to revision before bound-volume publication, while current document links expose no historical revision ledger or first-issued byte inventory. Current PDFs or later bound volumes therefore cannot prove 2021-2023 point-in-time content.
stage: source-audit
kpi_version: nlrb-board-decisions-source-screen-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:source-audit
  - strategy:nlrb-board-decisions
  - status:rejected
next_step: Screen a genuinely different free official date-publication family with first-release bytes or an auditable revision ledger; do not acquire NLRB PDFs, map captions, or load returns.
---

`ABANDON_NLRB_BOARD_DECISIONS_SOURCE`; `preregistered=false`; `pdf_inventory_acquired=false`; `issuer_mapping_performed=false`; `event_cube_opened=false`; `cells_completed=0`; `post_availability_outcomes_loaded=false`. The fixed 527-symbol training sample remains coverage-limited, not full market. Strict mapping would have accepted only captioned respondent legal entities exactly equal to a frozen SEC issuer title, with no brand, subsidiary, parent, union-party, acronym, fuzzy, or manual alias inference, but mapping was never reached. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
