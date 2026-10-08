# Local fallback memory: SEC EFFECT source rejection

summary: Exact SEC EFFECT was rejected at the metadata-only semantic gate. Twelve complete official 2021-2023 EDGAR quarterly master indexes contain 14,636 exact EFFECT rows (6,045/4,509/4,082), and direct one-to-one CIK matching in the frozen 527-symbol sample gives a loose upper bound of 160 pairs across 99 issuers. SEC's official definition mixes registration-statement effectiveness and post-effective amendments, while exact EFFECT metadata does not expose a homogeneous underlying filing action. No filing index, underlying form, body, or outcome was opened.

stage: sec-effect-source-semantics

kpi_version: versionless-source-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-semantics, strategy:sec-effect, status:failed-experiment

next_step: Freeze exact EFFECT without rescuing it through S-1, S-3, S-3ASR, post-effective amendments, 424B5, FWP, withdrawals, or manually inferred accession links. Move to exact original S-3ASR as a separately preregistered issuer-direct event family. Keep outcomes closed until immutable acceptance metadata, direct identity, source semantics, and coverage all pass.
