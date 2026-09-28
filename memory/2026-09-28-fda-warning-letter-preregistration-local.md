---
type: strategy-hypothesis
summary: Preregistered an FDA Warning Letter public-posting mean-reversion screen for the fixed 2021-2023 527-symbol coverage-limited sample. Availability uses Posted Date rather than private Letter Issue Date; only exact one-to-one legal-name matches are allowed. Five fixed subject families, a strict metadata coverage gate, and an exact 400-cell 9/18 bp plus delay diagnostic are frozen before XLSX acquisition or outcome access.
stage: preregistration
kpi_version: fda-warning-letter-training-feasibility-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - market:us
  - freq:5min
  - stage:preregistration
  - strategy:fda-warning-letter
  - status:planned
next_step: Acquire and hash the single official XLSX sequentially, build only the metadata/exact-name coverage snapshot, and stop before returns unless every frozen coverage threshold passes.
---

Official FDA evidence separates Posted Date from Letter Issue Date, says Warning Letters should be posted after redaction, and says they are not removed unless rescinded or amended. The contract uses first sample session strictly after Posted Date, five-session life, exact legal-name equality under a fixed canonicalizer, and no brand/subsidiary/parent/alias inference. Five priority-ordered subject families are clinical/research integrity, tobacco/ENDS, food/supplier controls, unapproved/misbranded, and manufacturing quality. Coverage requires 100 issuers, 500 exact symbol-letter events, every family with 50 events and 10 per year, and 40 availability sessions per family across all three years. Failure means zero outcome cells. Passing coverage alone permits the frozen 400-cell training diagnostic, not development data, version creation, Paper, pool, broker, or order actions. No XLSX or post-event return was loaded at preregistration. MCP memory search/create remain unavailable, so this tagged local fallback needs later backfill.
