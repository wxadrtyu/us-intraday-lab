---
type: data-decision
summary: DOL official PDF capture hit a transient HTTP 502 after four exact archive PDFs; the same fifth official URL returned HTTP 200 on a read-only HEAD check. Bounded retry for only HTTP 502/503/504 was added without changing source URL, request cadence, or frozen inventory.
stage: source-acquisition
kpi_version: dol-ui-claims-training-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-acquisition
  - strategy:dol-ui-claims-training-v1
  - status:running
next_step: Resume sequential capture from the frozen 156-URL official source inventory, preserving existing raw bytes and failing closed on hash changes.
---

The first four saved files are 2021-01-07, 2021-01-14, 2021-01-21, and 2021-01-28. The next frozen URL is `https://oui.doleta.gov/press/2021/020421.pdf`; a separate HEAD check returned `200 OK`. Retry is limited to three attempts with 2- and 4-second backoff. HTTP 404, redirects, altered source bytes, and exhausted transient errors still fail closed. Seven focused tests and Ruff passed before resumption. MCP memory search/create was unavailable, so this tagged local record is the required fallback for later MCP backfill.
