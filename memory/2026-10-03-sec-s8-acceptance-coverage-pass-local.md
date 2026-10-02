# Local fallback memory: SEC original Form S-8 acceptance-coverage pass

summary: The exact original SEC Form S-8 source passed the frozen acceptance-metadata coverage gate for the 2021-2023 527-symbol coverage-limited sample. All 620 one-to-one direct-CIK official filing-index pages were fetched sequentially with zero failures, 620 distinct hashes, and zero duplicate-byte groups; every page has a consistent accession, accepted timestamp, and exactly one S-8 primary-document row. Honest next-session mapping excludes 138 pairs with no later frozen sample session and retains 482 admissible pairs across 258 issuers. Yearly pairs are 220/150/112, yearly issuers 175/130/93, 62 issuers have at least three events, and maximum concentration is 1.66%; every fixed gate passes. No primary-document body or post-acceptance outcome was opened.

stage: metadata-only-coverage-gate

kpi_version: versionless-sec-original-s8-coverage-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:metadata-only-coverage-gate, strategy:sec-original-s8, status:coverage-passed, source:sec-edgar, sample:coverage-limited-527

next_step: Before loading outcomes, present and freeze a separate training design covering exact signal families, event lifetime, score direction, the 400-cell grid, 9/18 bp costs, one delayed-entry tier, retention gates, immutable inputs, and missingness. Obtain the required design approval, then implement and run only against frozen 2021-2023 training data. A training pass may only support recommending development-data acquisition; it does not authorize development/consumed loading, version creation, Paper activation, pool changes, broker actions, or order routing.

## Frozen evidence

`decision=PASS_SEC_S8_ACCEPTANCE_COVERAGE_GATE`; `source_original_s8=7909`; `candidate_pairs=620`; `filing_indexes_fetched=620`; `filing_index_failures=0`; `filing_index_bytes=5277737`; `distinct_filing_index_sha256=620`; `duplicate_hash_groups=0`; `coverage_artifact_sha256=62943eb65d564e07960efcd206563adf1baebd5715d0c2db30a56cbe15be2ca8`; `admissible_pairs=482`; `distinct_issuers=258`; `year_pairs=220/150/112`; `year_issuers=175/130/93`; `issuers_with_three_events=62`; `max_issuer_share=0.016597510373443983`; `missing_next_session=138`; `coverage_passed=true`; `primary_document_bodies_opened=false`; `cells_completed=0`; `post_acceptance_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
