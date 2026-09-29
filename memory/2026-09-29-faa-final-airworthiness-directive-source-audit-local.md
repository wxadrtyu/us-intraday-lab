# Local fallback memory: FAA final Airworthiness Directives

summary: Official FAA/Federal Register metadata supports a point-in-time ordinary final-AD family. The exact two-page API snapshot has 1,267 hits and 1,261 AD-title rules. Freezing title prefix, action exactly Final rule, and excluding superseding abstracts leaves 687 ordinary non-superseding final ADs (287/225/175 in 2021/22/23). Coverage is preregistered before mapping: 20 issuers, 300 symbol-doc pairs, 75 pairs and 10 issuers per year, 15 issuers with at least three events, max issuer share 25%, and complete next-session availability. Only exact affected Type Certificate Holder legal-name matches to one frozen SEC issuer are allowed. No PDF corpus, mapping, event cube, or outcome has been opened; cells_completed is zero.
stage: coverage_preregistration
kpi_version: frozen_event_cube_2021_2023_527_coverage_limited
memory_type: strategy-hypothesis
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:coverage_preregistration
  - strategy:faa_final_airworthiness_directive
  - status:preregistered
next_step: Sequentially acquire and hash only the 687 official GovInfo PDFs, audit completeness/corrections, then perform metadata-only strict Type Certificate Holder mapping and the frozen coverage gate. Do not load post-publication returns before every coverage condition passes.
