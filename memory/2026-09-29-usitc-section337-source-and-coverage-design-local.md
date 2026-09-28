---
type: data-decision
summary: Official Federal Register/GovInfo publication semantics make USITC Section 337 institution notices point-in-time feasible for a metadata-only coverage screen. The fixed 2021-2023 International Trade Commission full-text query returns 148 records; the frozen title literal excludes three documented false positives and retains 145 institution notices, 50/60/35 by publication year. Official USITC calendar-year statistics independently report 52/59/37 investigations. Preregistered exact official GovInfo PDFs, next-session availability, respondent-only exact frozen-SEC-title mapping, five fixed product-title families, and hard coverage floors of 25 issuers, 75 symbol-documents, 15 per year, and 8 events plus 5 dates per family. No corpus, mapping, event cube, outcomes, or 400-cell grid was opened; grid design is authorized only after coverage passes.
stage: coverage-design
kpi_version: usitc-section337-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:coverage-design
  - strategy:usitc-section337
  - status:preregistered
next_step: Sequentially acquire and hash the exact API response and all 148 official GovInfo PDFs, then run only the frozen respondent-role exact-name and calendar coverage audit. Freeze immediately if any gate fails; load no post-availability return before all coverage gates pass.
---

Decision is `SOURCE_FEASIBLE_FOR_COVERAGE_PREREGISTRATION`. The source-audit manifest SHA-256 is `5591ee0820267d5d34b76e97f1d585469f0e70da313572dd5795f12967fbe930`; raw API response SHA-256 is `0c860f90ac91dd39862b5e7990e14025a10110a0e270bfed9e60581b78f44f32`. The 527-symbol sample is coverage-limited, not full market. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
