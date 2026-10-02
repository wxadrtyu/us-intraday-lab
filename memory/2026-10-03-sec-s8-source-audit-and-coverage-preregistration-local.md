# Local fallback memory: SEC original Form S-8 source audit and coverage preregistration

summary: The exact original Form S-8 family is frozen as one issuer-filed employee-benefit securities registration event per accepted EDGAR accession. Twelve complete official 2021-2023 master indexes contain 7,909 exact S-8 filings (2,806/2,527/2,576) and 5,375 separately excluded S-8 POS filings. A pre-acceptance audit corrected an inadmissible all-period 809-symbol view to the frozen 2021-2023 527-symbol boundary. The one ambiguous frozen CIK, 1652044 for GOOG/GOOGL, is excluded under the one-to-one identity contract. Corrected direct-CIK matching gives a coarse upper bound of 300 issuers and 620 pairs, yearly pairs 225/196/199, yearly issuers 180/166/165, 98 repeat issuers, and 1.29% maximum concentration. Source volume passes, but coverage remains pending sequential filing-index acquisition, immutable hashes, acceptance timestamps, exact accession consistency, exactly one S-8 primary-document identity, and a later frozen sample session.

stage: source-audit-and-coverage-preregistration

kpi_version: versionless-sec-original-s8-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-audit-and-coverage-preregistration, strategy:sec-original-s8, status:pending, source:sec-edgar, sample:coverage-limited-527

next_step: Sequentially acquire and hash all 620 one-to-one direct-CIK official filing-index HTML pages. Parse immutable accession, SEC acceptance datetime, and exactly one primary-document row of type S-8 while leaving the full submission and document body unopened; retain all missingness and exclude invalid or end-censored pairs. Recompute the frozen independent coverage gates on admissible pairs before reading any filing economics or post-acceptance outcome. Fail closed on source inconsistency, systematic missingness, version ambiguity, or any coverage shortfall; never add S-8 POS or another form to rescue coverage.

## Frozen evidence

`family=exact-original-S-8`; `official_master_indexes=12`; `all_market_original_s8=7909`; `all_market_year_counts=2806/2527/2576`; `excluded_s8_pos=5375`; `frozen_sample_symbols=527`; `ambiguous_ciks_excluded=1`; `ambiguous_cik=1652044`; `coarse_sample_issuers=300`; `coarse_sample_pairs=620`; `coarse_year_pairs=225/196/199`; `coarse_year_issuers=180/166/165`; `coarse_issuers_with_three_events=98`; `coarse_max_issuer_share=0.012903225806451613`; `acceptance_metadata_complete=false`; `coverage_passed=false`; `cells_completed=0`; `post_acceptance_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
