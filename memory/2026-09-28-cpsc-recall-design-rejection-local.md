---
type: failed-experiment
summary: CPSC recall data were rejected before preregistration because RecallDate lacks content-version evidence, LastPublishDate is undocumented, the current CSV omits it, and no official historical revision ledger or first-vintage recovery was found. No archive, matches, coverage, or returns were loaded.
stage: design-screen
kpi_version: cpsc-recall-announcement-v0
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:design-screen
  - strategy:cpsc-recall-announcement-v0
  - status:frozen-rejected
next_step: Screen a genuinely different official dated-release family whose public event date and exact legal entity can be audited before metadata acquisition.
---

Decision `ABANDON_CPSC_RECALL_SOURCE` is final for the current-page/current-API/current-CSV contract. Official pages expose RecallDate but not publication time or revision history. API guides list LastPublishDate without defining its semantics, and the current full CSV omits that field. Weekly aggregate updates and daily remedy changes prove mutability; today's S3 version id can freeze only today's object, not reconstruct 2021–2023 content. Exact manufacturer/importer/distributor mapping would therefore leak current text if assigned to RecallDate. The frozen event cube is a 527-symbol coverage-limited sample, not the full market. Full archive, issuer matches, coverage, training cells, and post-announcement returns accessed: 0. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
