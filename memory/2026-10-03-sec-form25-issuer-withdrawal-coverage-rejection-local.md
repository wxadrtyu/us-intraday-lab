# Local fallback memory: SEC Form 25 issuer-withdrawal coverage rejection

summary: Complete official 2021-2023 EDGAR quarterly master indexes contain 6,621 original Form 25 or 25-NSE filings, split into 345 issuer-filed Form 25 and 6,276 exchange-filed Form 25-NSE, plus 72 excluded amendments. The economically bounded issuer-withdrawal upper bound admits original Form 25 only; exact frozen CIK matching finds 12 issuers and 13 pairs, yearly pairs 6/1/6, yearly issuers 6/1/5, zero issuers with three events, and 15.38% maximum concentration. It fails the fixed pair, yearly, and repeat-event coverage gates before filing-body or return access. Form 25-NSE cannot rescue the line because it is exchange-filed and mixes maturities, redemptions, mergers, transfers, substitutions, listing-standard removals, and other distinct actions.

stage: metadata-only-coverage-gate

kpi_version: versionless-sec-form25-issuer-withdrawal-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:metadata-only-coverage-gate, strategy:sec-form25-issuer-withdrawal, status:rejected, source:sec-edgar, sample:coverage-limited-527

next_step: Freeze original Form 25 without adding Form 25-NSE, subdividing exchange actions post hoc, relaxing coverage, fetching filing bodies, or reading outcomes. Move to a genuinely different issuer-direct official family. Audit original SEC Form S-8 employee-benefit securities registration statements as a capital-and-compensation event family, keeping S-8 POS, amendments, resale registrations, and other forms separate. First prove source semantics, complete official-index volume, immutable accession and primary-document identity, acceptance timing, amendment chains, direct CIK coverage, and an independent metadata-only coverage gate; abandon before outcomes at the first failed gate.

## Frozen evidence

`decision=ABANDON_SEC_FORM25_ISSUER_WITHDRAWAL_COVERAGE_GATE`; `official_master_indexes=12`; `source_artifact_sha256=99065b17ea4d3a1a0bfa2755c0bc5c1d7919f5123c9db5cf3e0cf68052af4651`; `original_form25_or_25_nse=6621`; `all_market_year_counts=2124/2087/2410`; `original_form25=345`; `original_form25_nse=6276`; `excluded_amendments=72`; `sample_upper_bound_issuers=12`; `sample_upper_bound_pairs=13`; `year_pairs=6/1/6`; `year_issuers=6/1/5`; `issuers_with_three_events=0`; `max_issuer_share=0.15384615384615385`; `filing_bodies_acquired=false`; `acceptance_timing_audited=false`; `coverage_passed=false`; `cells_completed=0`; `post_filing_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
