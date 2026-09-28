---
type: data-decision
summary: CPSC recall pages provide dated public announcements and structured firm roles, but the current archive is mutable and the official guide does not define LastPublishDate or retain revision history. Source feasibility remains pending; no full archive, issuer coverage, or returns were accessed.
stage: source-feasibility
kpi_version: cpsc-recall-announcement-v0
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-feasibility
  - strategy:cpsc-recall-announcement-v0
  - status:pending-publication-semantics
next_step: Establish official LastPublishDate semantics; reject if unavailable, otherwise preregister a metadata-only exact-issuer coverage audit before acquisition or outcomes.
---

The official recall pages expose recall dates and numbers, while the API guide adds a current-record `LastPublishDate` field without defining its revision semantics. CPSC explicitly says aggregate recall data update weekly and remedy data may change daily. The current 18,408,016-byte S3 CSV had Last-Modified 2026-09-25 20:29:24 UTC, ETag `90f891628aa5ecdb2acb3a9844599fe8-3`, and version id `tHfthjYK6txlMvybVkVa6qsk7iNMjUKc`; only a header range was read, and the CSV lacks LastPublishDate. Any later contract must use next-session availability and exact legal-name matches only, with no brand, subsidiary, parent, retailer, or alias inference. The frozen event cube is a 527-symbol coverage-limited sample, not the full market. Full archive, issuer matches, training cells, and post-announcement returns accessed: 0. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
