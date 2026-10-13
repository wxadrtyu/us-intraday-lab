---
type: data-decision
summary: Existing Polygon/Massive credential returned 403 NOT_AUTHORIZED for one read-only historical 5-minute aggregate probe; no alternate full-market technical source is currently entitled or staged.
stage: five-minute-alternative-source-entitlement
kpi_version: null
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - freq:intraday
  - status:source-access-gate
next_step: Continue read-only checks for an independently entitled full-market point-in-time technical feed; do not bulk download, splice providers, or read strategy returns until coverage and novelty are verified.
---

The 2023-12-29 AAPL historical five-minute REST aggregate probe used an
existing credential only in an authorization header and printed no secret or
price. HTTP 403 / NOT_AUTHORIZED means the current credential is not an
available replacement source. No local stock minute flat files or exchange
auction-imbalance history was found. Prior full-market joint route audit:
1/20 routes at 95% aggregate, but that route failed 37/96 monthly coverage
checks. No user data, broker path, or Paper state changed. MCP memory
search/create were unavailable; backfill this local record later.
