---
type: strategy-hypothesis
summary: Official Federal Register publication semantics and GovInfo official PDFs make environmental consent-decree notices point-in-time feasible. A fixed DOJ API source screen found 255 unique 2021-2023 Consent Decree title records, 96/81/78 by year. Preregistered conservative next-session availability, official GovInfo PDFs only, exact one-to-one defendant/SEC issuer-title equality, five fixed title families, a hard metadata-only coverage gate, and the standard 400-cell 9/18 bp plus one-bar-delay diagnostic. No corpus, mapping, event cube, or outcomes were opened at this checkpoint.
stage: preregistration
kpi_version: federal-register-consent-decree-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:preregistration
  - strategy:federal-register-consent-decree
  - status:preregistered
next_step: Acquire and hash the single exact Federal Register API response, reproduce the frozen 255 and 96/81/78 inventory, then sequentially acquire only official GovInfo PDFs and run the metadata-only exact-defendant coverage gate before opening any post-publication outcome.
---

The frozen sample is 527 symbols over 2021-2023 and is coverage-limited, not the full market. Availability is the first sample session strictly after printed publication date; prior-day public inspection is ignored. Coverage requires complete source/PDF evidence, 50 exact issuers, 200 symbol-document events, all three years, and fixed family/year/session floors. Failure is `ABANDON_FEDERAL_REGISTER_CONSENT_DECREE_COVERAGE_GATE` with `cells_completed=0`. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
