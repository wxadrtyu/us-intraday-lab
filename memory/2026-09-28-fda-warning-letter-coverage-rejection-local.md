---
type: failed-experiment
summary: The exact preregistered FDA Warning Letters standard XLSX export was acquired and hashed but failed the source-completeness coverage gate. The official index declares 3,701 items while the workbook contains exactly 1,000 rows, a 2,701-row shortfall. The separate batch-export endpoint was visible only as an unpreregistered alternative and was not used to rescue the line after inspection. The line is frozen before issuer mapping, event-cube access, or any post-availability return read.
stage: coverage-gate
kpi_version: fda-warning-letter-training-feasibility-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:coverage-gate
  - strategy:fda-warning-letter
  - status:rejected
next_step: Audit a genuinely different high-volume free official date-publication family, beginning with NLRB Board Decisions and Orders, for immutable issue-date/PDF semantics and exact captioned legal-entity mapping before preregistration or acquisition.
---

Official index SHA-256 is `6671da67aa6712ab057ccc982d001bdf772e9d2a2459db1b3f09618ccd9f14b6`; exact standard XLSX SHA-256 is `7fc4481d2c37c2ed012718601f648d0f9b9fdc9b41d62257cec0f198c7635c7d`; external manifest SHA-256 is `26891bb5772b1aa0adcb5b951e6341b448de7a41fc3ef34bb390f8e7c9d8ae24`. The workbook has the seven expected columns and 647 rows dated 2021-2023, distributed 94/548/5. These are incomplete-source diagnostics, not issuer coverage. `ABANDON_FDA_WARNING_LETTER_COVERAGE_GATE`; `cells_completed=0`; `post_availability_outcomes_loaded=false`. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
