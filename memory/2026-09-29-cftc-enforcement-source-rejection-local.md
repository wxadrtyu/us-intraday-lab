---
type: failed-experiment
summary: CFTC 2021-2023 enforcement press releases and linked complaint/order documents failed the preregistration source gate. Official pages retain release numbers and displayed dates, but the current archive provides no historical first-publication receipt or page/attachment version ledger. CFTC release 7366-16 explicitly says the numbered release was edited for technical corrections and other adjustments to the attached order while retaining the original May 9, 2016 date and showing a July 20, 2016 update. Current CDN Last-Modified headers cannot recover 2021-2023 first-publication state. Official gross totals are 55, 82, and 96 actions, but volume cannot repair the point-in-time defect. No complete inventory, mapping, event cube, or outcomes were opened.
stage: source-gate
kpi_version: cftc-enforcement-releases-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:source-gate
  - strategy:cftc-enforcement-releases
  - status:rejected
next_step: Preserve the official-page and header hashes. Do not infer first publication from release date, release number, current content, or current Last-Modified. Audit a genuinely different free official high-frequency dated-event family with explicit public availability and recoverable first-version bytes before preregistration or outcome access.
---

Decision is `ABANDON_CFTC_ENFORCEMENT_RELEASE_SOURCE`; `source_point_in_time=false`, `preregistered=false`, `full_index_acquired=false`, `pleading_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, and `post_availability_outcomes_loaded=false`.

External source-audit manifest SHA-256 is `17d91138e70a54d168f738e2f01e87cdab3545e54aa2c7a85ebb619065a2308a`. The 527-symbol 2021-2023 sample remains coverage-limited, not full market. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
