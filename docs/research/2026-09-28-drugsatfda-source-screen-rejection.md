# Drugs@FDA approval-action source screen

Decision: **REJECT_DRUGSATFDA_ACTION_DATE_SOURCE**. This genuinely different official-source line was screened only after the Daily Treasury Statement design was frozen. It was rejected before preregistration, acquisition, issuer matching, coverage measurement, or any return read. The frozen 2021–2023 event cube remains a **527-symbol coverage-limited sample, not the full US market**.

## Official-source evidence

FDA describes [Drugs@FDA](https://www.fda.gov/drugs/drug-approvals-and-databases/about-drugsfda) as a database updated daily. Its downloadable [data files](https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files) are current database extracts updated each weekday morning. Those pages provide action dates, sponsor names, and document dates, but they do not provide historical daily database snapshots or the timestamp at which a particular approval became publicly observable.

FDA's documented internal process separates the regulatory action from later disclosure review and web publication: the approval letter and action package enter an electronic archive, undergo disclosure review, and are then converted and published in Drugs@FDA. The action date is therefore not a public-release timestamp.

Revision risk is concrete rather than hypothetical. FDA approval-letter archives contain replacement approval letters that correct earlier letters while retaining the original effective approval date. A current action record or currently served PDF can consequently encode later information under an unchanged action date.

## Gate result

A next-trading-day rule based on `ActionDate` would assume same-day public availability that the official process does not establish. A conservative fixed delay would not solve the missing per-record publication timestamp or replacement-history problem. Current daily extracts also cannot reconstruct what was visible on each historical date.

- Historical first-publication timestamp gate: fail.
- Historical first-vintage content gate: fail.
- Issuer mapping attempted: no.
- Training events or cells evaluated: 0.
- Post-event returns loaded: no.
- Reopening by adding an inferred lag: forbidden.

This decision freezes only the Drugs@FDA action-date/current-extract contract. A future FDA line would require a separate immutable, timestamped announcement archive and a preregistered exact issuer map; it may not inherit the action dates or current extracts rejected here.

Next source screen should test an official dated-announcement family whose public date is the event itself, while still rejecting current mutable indexes and ambiguous parent/subsidiary mappings before outcomes.
