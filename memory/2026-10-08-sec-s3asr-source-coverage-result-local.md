# Local fallback memory: SEC exact original S-3ASR source coverage result

summary: Exact original SEC S-3ASR passed the frozen metadata-only acceptance coverage gate. All 357 direct-CIK candidate filing-index pages were fetched sequentially with zero failures, 357 distinct SHA-256 values, zero duplicate-byte groups, matching accessions and acceptance timestamps, and exactly one type S-3ASR primary row each. Seventy-one pairs were explicitly excluded only because the frozen sample had no later trading session. The admitted set has 286 pairs and 249 issuers; yearly pairs are 122/88/76, yearly issuers 113/82/71, six issuers have at least three events, and maximum concentration is 1.748%. Artifact SHA-256 is f0efbbd0d49bbb51e219ca016f280648ef3cae447a91cbdaefef1977a5d013de. No primary body or outcome was opened.

stage: sec-s3asr-source-coverage

kpi_version: versionless-source-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-coverage, strategy:sec-original-s3asr, status:passed

next_step: Write and freeze a separate causal training design before opening outcomes. Preserve S-3ASR as an automatic shelf-registration event rather than a completed offering or capital raise. Fix event life, signal families, exact bounded grid, 9/18bp costs, one-delay stress, retention gates, missingness, and stop rule. Keep primary bodies, 424B5, FWP, EFFECT, S-3, amendments, linked financings, development/consumed data, versions, monitoring, and execution out of scope.
