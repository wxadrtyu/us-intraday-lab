---
type: failed-experiment
summary: Drugs@FDA approval action dates and current weekday extracts were rejected as a historical event source because regulatory action dates are not web-publication timestamps and replacement letters can retain the original effective date. No issuer matching, coverage, or returns were accessed.
stage: source-feasibility
kpi_version: drugsatfda-action-date-v0
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-feasibility
  - strategy:drugsatfda-action-date-v0
  - status:frozen-rejected
next_step: Screen a separate official dated-announcement family with auditable public event dates and strict exact issuer mapping; do not reuse Drugs@FDA action dates or current extracts.
---

Decision `REJECT_DRUGSATFDA_ACTION_DATE_SOURCE` freezes this contract before preregistration. FDA states that Drugs@FDA and its downloadable files are updated daily, but does not expose historical daily snapshots or record-level first-publication timestamps. The official workflow places disclosure review and web publication after the regulatory action, so `ActionDate` is not a point-in-time availability field. Replacement approval letters can preserve the original effective approval date, proving that current documents are not necessarily first-vintage content. The frozen event cube is a 527-symbol coverage-limited sample, not the full market. Issuer matches, training events/cells, and post-event returns accessed: 0. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
