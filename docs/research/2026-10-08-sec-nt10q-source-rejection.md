# SEC original Form NT 10-Q source rejection

Decision: **ABANDON_SEC_NT10Q_COVERAGE_GATE**. This is a metadata-only source
rejection. No filing-index page, filing body, primary document, or
post-availability return was opened for this family.

## Frozen family and semantics

The proposed family was exact original form type `NT 10-Q`: an issuer's Form
12b-25 notification that its quarterly report cannot be filed timely without
unreasonable effort or expense. The event would have been one exact issuer
accession at its SEC acceptance timestamp. `NT 10-Q/A`, `NT 10-K`,
`NT 10-K/A`, late-filed 10-Q reports, 8-K disclosures, press releases, and all
other forms were excluded and could not be mixed in to increase coverage.

Issuer identity was restricted to exact one-to-one numeric CIK matching against
the frozen SEC identity snapshot. CIK 1652044 was excluded because it maps to
both GOOG and GOOGL. Security-name inference, parent/subsidiary mapping, former
names, abbreviations, fuzzy matching, and manual aliases were forbidden.

## Complete official metadata census

The audit reused the 12 already-frozen official quarterly EDGAR master archives
for 2021-2023 and filtered by exact form equality `NT 10-Q`. The complete
all-market census contains 5,452 original accessions: 1,880 in 2021, 1,632 in
2022, and 1,940 in 2023. Fifty-four `NT 10-Q/A` accessions were separately
observed and excluded.

Within the frozen 527-symbol 2021-2023 coverage-limited sample, direct
one-to-one CIK matching yields only 7 issuer-accession pairs across 6 issuers.
Yearly pair counts are 4/0/3 and yearly issuer counts are 4/0/2. No issuer has
three events. The largest issuer contributes 2/7 pairs, or 28.57%.

## Gate decision

The fixed pre-outcome coverage gate requires at least 10 issuers, 50 pairs, at
least 12 pairs and 5 issuers in each year, at least 6 issuers with three events,
and no issuer above 25%. Every requirement except immutable source volume fails
at the coarse direct-CIK upper bound. Filing-index acquisition, acceptance-time
validation, next-session mapping, and stricter missingness can only reduce this
upper bound.

The family is frozen without acquiring filing-index pages or evaluating a
return grid. No threshold, form definition, identity rule, or year boundary was
changed after observing the shortfall. `NT 10-K`, amendments, and other late
filing forms remain separate event families and are not rescue data.

Final state: `all_market_original_nt10q=5452`,
`all_market_year_counts=1880/1632/1940`, `excluded_nt10q_amendments=54`,
`frozen_sample_symbols=527`, `coarse_pairs=7`, `coarse_issuers=6`,
`coarse_year_pairs=4/0/3`, `coarse_year_issuers=4/0/2`,
`coarse_issuers_with_three_events=0`, `coarse_max_issuer_share=0.2857142857`,
`filing_indexes_fetched=0`, `event_cube_opened_for_outcomes=false`,
`cells_completed=0`, `strategy_versions_created=0`, `paper_activation=false`,
and `order_route=FORBIDDEN`.
