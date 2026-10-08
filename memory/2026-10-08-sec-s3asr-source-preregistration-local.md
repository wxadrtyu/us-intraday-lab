# Local fallback memory: SEC exact original S-3ASR source preregistration

summary: Exact original SEC S-3ASR is preregistered as a homogeneous issuer automatic-shelf-registration family, not an offering or capital-raised event. Twelve frozen official 2021-2023 EDGAR master indexes contain 5,766 originals (2,165/1,508/2,093). Direct one-to-one frozen CIK matching gives a coarse upper bound of 357 pairs across 295 issuers, yearly pairs 126/95/136, yearly issuers 117/87/123, 11 issuers with at least three events, and 1.96% maximum concentration. S-3ASR/A and all other forms are excluded. Outcome columns remain closed.

stage: sec-s3asr-source-preregistration

kpi_version: versionless-source-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-preregistration, strategy:sec-original-s3asr, status:preregistered

next_step: Sequentially fetch and SHA-256 all 357 official filing-index pages. Require matching accession, acceptance timestamp, exactly one type S-3ASR primary row, and a later frozen sample session. Retain all failures and duplicate-byte evidence. Apply the frozen 10 issuer, 50 pair, annual 12 pair and 5 issuer, six repeat-issuer, 25 percent concentration, and all-next-session gates before any outcome access. If coverage passes, write a separate causal signal-design preregistration; do not load returns yet.
