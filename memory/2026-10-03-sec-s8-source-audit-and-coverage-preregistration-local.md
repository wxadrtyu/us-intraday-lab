# Local fallback memory: SEC original Form S-8 source audit and coverage preregistration

summary: The exact original Form S-8 family is frozen as one issuer-filed employee-benefit securities registration event per accepted EDGAR accession. Twelve complete official 2021-2023 master indexes contain 7,909 exact S-8 filings (2,806/2,527/2,576) and 5,375 separately excluded S-8 POS filings. The one ambiguous frozen CIK, 1652044 for GOOG/GOOGL, is excluded under the one-to-one identity contract. Corrected direct-CIK matching gives a coarse upper bound of 431 issuers and 871 pairs, yearly pairs 312/281/278, yearly issuers 254/239/230, 136 repeat issuers, and 0.92% maximum concentration. Source volume passes, but coverage remains pending sequential full-submission acquisition, immutable hashes, acceptance timestamps, exact accession consistency, exactly one S-8 primary-document identity, and a later frozen sample session.

stage: source-audit-and-coverage-preregistration

kpi_version: versionless-sec-original-s8-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-audit-and-coverage-preregistration, strategy:sec-original-s8, status:pending, source:sec-edgar, sample:coverage-limited-527

next_step: Sequentially acquire and hash all 871 one-to-one direct-CIK official filing-index HTML pages. Parse immutable accession, SEC acceptance datetime, and exactly one primary-document row of type S-8 while leaving the full submission and document body unopened; retain all missingness and exclude invalid or end-censored pairs. Recompute the frozen independent coverage gates on admissible pairs before reading any filing economics or post-acceptance outcome. Fail closed on source inconsistency, systematic missingness, version ambiguity, or any coverage shortfall; never add S-8 POS or another form to rescue coverage.

## Frozen evidence

`family=exact-original-S-8`; `official_master_indexes=12`; `all_market_original_s8=7909`; `all_market_year_counts=2806/2527/2576`; `excluded_s8_pos=5375`; `ambiguous_ciks_excluded=1`; `ambiguous_cik=1652044`; `coarse_sample_issuers=431`; `coarse_sample_pairs=871`; `coarse_year_pairs=312/281/278`; `coarse_year_issuers=254/239/230`; `coarse_issuers_with_three_events=136`; `coarse_max_issuer_share=0.009184845005740528`; `acceptance_metadata_complete=false`; `coverage_passed=false`; `cells_completed=0`; `post_acceptance_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
