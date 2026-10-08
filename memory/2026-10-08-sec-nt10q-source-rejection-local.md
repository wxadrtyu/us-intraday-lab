# Local fallback memory: SEC original Form NT 10-Q source rejection

summary: Exact original SEC Form NT 10-Q was rejected at the metadata-only direct-CIK coverage gate. Twelve complete official 2021-2023 EDGAR quarterly master indexes contain 5,452 originals (1,880/1,632/1,940) and 54 separately excluded NT 10-Q/A amendments. In the frozen 527-symbol coverage-limited sample, exact one-to-one CIK matching yields only 7 pairs across 6 issuers, yearly pairs 4/0/3, yearly issuers 4/0/2, zero issuers with three events, and 28.57% maximum concentration. No filing index, body, primary document, or post-availability return was opened.

stage: sec-nt10q-source-coverage

kpi_version: versionless-source-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-coverage, strategy:sec-original-nt10q, status:failed-experiment

next_step: Freeze exact NT 10-Q without adding NT 10-K, amendments, late-filed reports, 8-K, or press releases. Move to a genuinely different issuer-direct official event family. Continue metadata-only source semantics, immutable timing/identity, and coverage gates before any outcome access. Do not tune thresholds, load development/consumed data, create a version, or touch Paper/execution state.
