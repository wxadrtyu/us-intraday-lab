---
type: data-decision
summary: Official NYSE and Databento documentation identifies venue-specific historical auction imbalance as a distinct technical-data candidate, but no entitled local historical API or full-market point-in-time execution-path audit exists; data gate remains closed.
stage: five-minute-auction-source-feasibility
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - status:source-access-gate
next_step: Obtain explicit historical auction-feed entitlement and spending ceiling; use metadata/cost calls first, then a pre-registered finite multi-venue coverage and executable-path audit before any material download or return test.
---

The local process exposes Polygon/Massive credential names but not a
Databento historical API key. Local staging/acquired directories contained no
historical exchange auction-imbalance feed. NYSE sells separate imbalance
histories for NYSE, American, and Arca. Databento documents historical
Nasdaq/NYSE imbalance schemas with account-specific metadata and cost methods.
Neither product description proves 95% full-universe signal-entry-exit
coverage. Nasdaq NOII near/far prices are unavailable before 09:28/15:55 ET.
No download, purchase, return evaluation, broker action, or pool change was
made. MCP memory search/create were unavailable in this environment; backfill
this record when available.
