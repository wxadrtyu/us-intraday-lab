# Local fallback memory: FINRA short-volume duplicate family

summary: The proposed FINRA Reg SHO daily short-sale volume continuation was rejected as a duplicate exhausted family. The exact Consolidated NMS source was already audited and coverage-gated on 2026-09-17: 381,084 of 388,745 event rows covered across 743 sessions, followed by a complete frozen 400-cell training diagnostic with zero retained cells and decision ABANDON_FINRA_SHORT_VOLUME_NO_VERSION_CREATED. This turn acquired no files, performed no new symbol mapping, did not open the event cube, read no new outcome series, and completed zero new cells. Facility pooling, thresholds, rolling windows, missingness, and symbol rules may not be retuned after the failure.

stage: duplicate-family-gate

kpi_version: versionless-finra-short-volume-duplicate-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:duplicate-family-gate, strategy:finra-short-volume, status:rejected, source:finra, sample:coverage-limited-527

next_step: Audit SEC 2021-2023 official Fails-to-Deliver data as a genuinely different settlement-failure source, separate from SEC issuer filings, administrative proceedings, trading suspensions, and FINRA short-volume flow. First prove the official semi-monthly file release schedule and actual public availability, archive completeness, stable file identity, corrections/replacements, settlement-date semantics, and point-in-time symbol handling. Before any outcome read, predefine one self-normalized, economically homogeneous FTD event construction using only prior available FTD history, with fixed missingness and coverage gates. Do not use current shares outstanding, infer symbol histories, fold share classes, or map issuers, parents, subsidiaries, brands, former names, fuzzy matches, or manual aliases. Freeze and switch if availability, historical identity, construction, event volume, or exact-symbol coverage cannot be proven.

## Frozen evidence

Prior tracked artifacts show coverage PASS followed by `cells_completed=400`, `retained_cells=0`, and `strategy_versions_created=0`. `ABANDON_FINRA_SHORT_VOLUME_DUPLICATE_FAMILY`; `new_cells_completed=0`; `new_post_availability_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
