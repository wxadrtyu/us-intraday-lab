---
type: failed-experiment
summary: USITC Section 337 institution notices fail the preregistered metadata-only coverage gate even under a deliberately permissive issuer-mention upper bound.
stage: source-coverage-gate
kpi_version: usitc-section337-v1
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-coverage-gate
  - strategy:usitc-section337-institution
  - status:abandoned
next_step: Audit a genuinely different free official event family with point-in-time publication semantics and adequate strict issuer coverage before any outcomes are loaded.
---

# Local fallback memory

MCP memory was unavailable, so this stage conclusion is stored locally for later backfill.

The hash-frozen Federal Register source produced 145 retained institution notices and all 145 official GovInfo PDFs were acquired successfully. A deliberately permissive upper bound accepted exact frozen SEC issuer-title mentions anywhere in each target notice's scope segment, retained ambiguous keys and non-respondent mentions, and broadened seven scope-extraction exceptions to the whole prefix before the target FR Doc marker. Even that superset produced only 32/50/11 symbol-document pairs in 2021/2022/2023 and failed the frozen 15-per-year threshold in 2023. It also failed several family event/date gates. Therefore strict respondent-only one-to-one matching cannot pass.

Decision: `ABANDON_USITC_SECTION337_COVERAGE_GATE`; `cells_completed=0`; `strict_respondent_mapping_performed=false`; `post_availability_outcomes_loaded=false`. The coverage manifest SHA-256 is `44e22e8acc1e0d71a1b95f2d44bfdbfe47515766fd78134ecb0c7215300f848c`. Do not reopen this source by changing roles, aliases, notice types, families, sample, years, or thresholds.
