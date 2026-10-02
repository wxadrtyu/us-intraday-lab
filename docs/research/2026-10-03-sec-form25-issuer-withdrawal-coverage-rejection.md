# SEC Form 25 issuer-withdrawal coverage rejection

Decision: **ABANDON_SEC_FORM25_ISSUER_WITHDRAWAL_COVERAGE_GATE**. The issuer-filed original Form `25` line is frozen at the metadata-only coverage upper bound, before any filing-body, acceptance-timestamp, or post-filing return read. The frozen event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Source and economic-family boundary

The source audit used the complete 12 official EDGAR quarterly master indexes for 2021-2023 at `https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.zip`. Each archive was retained with its byte count and SHA-256 in the untracked audit state. The frozen source-and-coverage artifact has SHA-256 `99065b17ea4d3a1a0bfa2755c0bc5c1d7919f5123c9db5cf3e0cf68052af4651`.

The indexes contain 6,621 original Form `25` or `25-NSE` filings: 2,124 in 2021, 2,087 in 2022, and 2,410 in 2023. They also contain 72 `25/A` or `25-NSE/A` amendments, which are excluded. The original population splits into 345 issuer-filed Form `25` filings and 6,276 exchange-filed Form `25-NSE` filings.

Only original Form `25` was admitted to the issuer-withdrawal upper bound. It is the ex-ante issuer-filed line associated with Rule 12d2-2(c). Form `25-NSE` was not mixed in: it is filed by exchanges under different rule provisions and spans heterogeneous actions including maturities, redemptions, retired or substituted securities, merger completions, exchange transfers, and listing-standard delistings. Its broad frozen-sample count cannot rescue the issuer-filed family. Any future `25-NSE` subtype would require an independent preregistration and document-level action classification before coverage, not a post-hoc subdivision of this failed line.

## Exact-CIK coverage upper bound

The screen mapped only the filing CIK to the frozen one-to-one SEC issuer identity. It used no security-name inference, former name, abbreviation, parent/subsidiary relationship, fuzzy match, or hand alias. Even before excluding issuer-filed transfers, reorganizations, or other housekeeping actions, original Form `25` reaches only:

- 12 distinct frozen issuers, but only 13 issuer-filing pairs, below 50;
- 6/1/6 pairs in 2021/2022/2023, below 12 in every year;
- 6/1/5 issuers by year, with 2022 below 5;
- 0 issuers with at least 3 events, below 6;
- a maximum issuer share of 2/13, or 15.38%.

The 13 permissive pairs are HON, BLDR, LCID, WOLF, PANW, BKR, TWLO, FISV twice, ROP, DASH, LIN, and EXPD. They are an upper bound, not assertions that every filing represents the same final delisting mechanism. A stricter legal-action family can only be smaller. The fixed coverage gate therefore fails decisively without acquiring or interpreting the 13 submissions.

Because coverage already fails, the audit did not fetch primary documents, inspect action checkboxes, reconstruct amendment or supersession chains, or establish accepted timestamps and first-sample-session availability. Those are later gates and cannot repair insufficient coverage. Only `symbol` and `session_date` were read from the hash-verified event cube; no return or outcome column was loaded. Final state: `source_original_form25=345`, `sample_upper_bound_issuers=12`, `sample_upper_bound_pairs=13`, `coverage_passed=false`, `filing_bodies_acquired=false`, `acceptance_timing_audited=false`, `event_cube_outcomes_opened=false`, `cells_completed=0`, `post_filing_outcomes_loaded=false`.

No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
