# SEC EFFECT source rejection

Decision: **ABANDON_SEC_EFFECT_SEMANTIC_GATE**. This is a metadata-only
semantic rejection. No filing-index page, filing body, underlying registration
statement, or post-availability return was opened for this family.

## Proposed family and fatal ambiguity

The proposed family was exact EDGAR form type `EFFECT`, one accession per
issuer at its acceptance timestamp. The complete official 2021-2023 quarterly
master indexes contain 14,636 exact `EFFECT` accessions: 6,045 in 2021, 4,509
in 2022, and 4,082 in 2023. Direct one-to-one CIK matching against the frozen
527-symbol sample gives a deliberately loose upper bound of 160 pairs across
99 issuers, with yearly pairs 77/46/37 and yearly issuers 60/37/27.

Source volume is not the problem. SEC's official EFFECT explanation states
that the notice covers both Securities Act registration statements and
post-effective amendments, except filings that become effective
automatically. Exact `EFFECT` metadata therefore does not identify one
homogeneous issuer action. Recovering the underlying registration type would
require a separately preregistered accession-linkage and legal-form audit; it
cannot be inferred from the EFFECT row itself.

Official evidence:

- <https://www.sec.gov/divisions/corpfin/cfacctdisclosureissues.pdf>
- <https://www.sec.gov/file/efmvol2-c3>

## Frozen decision

The family is rejected before acquisition and outcomes. It must not be rescued
by mixing S-1, S-3, S-3ASR, post-effective amendments, 424B5 prospectus
supplements, FWP filings, withdrawals, or manually inferred underlying
registrations. A future linked-underlying-form family would be a new source
contract with its own immutable relationship proof and coverage gate.

Final state: `all_market_exact_effect=14636`,
`all_market_year_counts=6045/4509/4082`, `coarse_pairs=160`,
`coarse_issuers=99`, `coarse_year_pairs=77/46/37`,
`coarse_year_issuers=60/37/27`, `filing_indexes_fetched=0`,
`underlying_forms_linked=0`, `event_cube_opened_for_outcomes=false`,
`cells_completed=0`, `strategy_versions_created=0`,
`paper_activation=false`, and `order_route=FORBIDDEN`.
