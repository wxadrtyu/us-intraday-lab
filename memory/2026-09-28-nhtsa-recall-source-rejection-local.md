---
type: data-decision
summary: Rejected NHTSA Safety Recalls/Part 573 at the preregistration source gate. Official documentation defines RCDATE as report received and DATEA as database record creation, while NHTSA describes a later sequence of recall-number assignment, acknowledgment, summarization, and entry into the public ODI system. Neither field is proven to be first web publication. Current daily bulk files, including historical-range ZIPs modified in 2026, provide no historical-vintage ledger, and current Part 573 PDFs do not expose a complete original/amendment byte timeline with first-public timestamps.
stage: source-audit
kpi_version: nhtsa-recall-source-screen-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:source-audit
  - strategy:nhtsa-recall
  - status:rejected
next_step: Audit Federal Register environmental consent-decree notices as a genuinely different dated-publication family, first proving official publication/PDF immutability, event volume, and exact named-defendant issuer mapping before preregistration.
---

`ABANDON_NHTSA_RECALL_SOURCE`; `preregistered=false`; `bulk_or_api_acquired=false`; `part573_inventory_acquired=false`; `issuer_mapping_performed=false`; `event_cube_opened=false`; `cells_completed=0`; `post_availability_outcomes_loaded=false`. No brand, make, model, importer, dealer, subsidiary, parent, supplier, acronym, fuzzy, or manual alias mapping was attempted. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
