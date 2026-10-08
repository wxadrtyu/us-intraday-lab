# SEC exact original S-3ASR source coverage result

Decision: **PASS_SEC_S3ASR_METADATA_COVERAGE**. This result authorizes only a
separate causal signal-design preregistration. It does not authorize outcome
access, development data, strategy version creation, monitoring, or execution.

## Immutable acquisition result

The audit used the 12 frozen official EDGAR quarterly master archives for
2021-2023 and exact form equality `S-3ASR`. It confirmed 5,766 all-market
original accessions, with 2,165/1,508/2,093 by year. The complete indexes had
zero exact `S-3ASR/A` rows; amendments nevertheless remain explicitly excluded
from the source contract.

Direct one-to-one frozen CIK matching produced the preregistered 357
issuer-accession candidates. CIK 1652044 remained excluded because it maps to
both GOOG and GOOGL. All 357 official filing-index pages were acquired
sequentially. Each page had a distinct SHA-256, a matching accession, an SEC
acceptance timestamp, and exactly one document row whose type was exactly
`S-3ASR`. There were no fetch, parse, identity, or primary-row failures and no
duplicate-byte groups.

Seventy-one otherwise valid pairs had no frozen sample trading session after
their acceptance date and were retained as explicit missingness. The remaining
286 admitted pairs cover 249 issuers. Filing-index bytes total 5,204,921. The
complete coverage artifact is:

- path: `state/sec_s3asr_source_audit/acceptance-coverage.json`
- SHA-256: `f0efbbd0d49bbb51e219ca016f280648ef3cae447a91cbdaefef1977a5d013de`

The local `state/` evidence remains deliberately untracked. Official URLs,
source archive hashes, filing-index hashes, parsed metadata, every admitted
row, and every missing row are preserved in the artifact.

## Frozen gate result

- issuer-document pairs: 286, threshold 50;
- distinct issuers: 249, threshold 10;
- pairs by year: 122/88/76, threshold 12 each;
- issuers by year: 113/82/71, threshold 5 each;
- issuers with at least three events: 6, threshold 6;
- maximum issuer share: 5/286 = 1.748%, ceiling 25%; and
- every admitted pair has a frozen sample session strictly after acceptance.

All fixed gates pass without changing the source family, thresholds, identity
rules, or time boundary. Primary-document bodies and exhibits were not opened.
The event cube was read only for `symbol` and `session_date`; no outcome column
was loaded and `cells_completed=0`.

## Boundary for the next stage

Before any return access, a new design must freeze the causal interpretation,
event life, mutually defined signal families, exact grid, costs, delay,
retention gates, missingness, and stop rule. `S-3ASR` remains an automatic
shelf-registration event and must not be relabeled as a completed offering or
capital raise. No 424B5, FWP, EFFECT, S-3, amendment, takedown, or linked
financing data may be introduced after this result.

Final state: `primary_document_bodies_opened=false`,
`post_acceptance_outcomes_loaded=false`, `cells_completed=0`,
`strategy_versions_created=0`, `paper_activation=false`, and
`order_route=FORBIDDEN`.
