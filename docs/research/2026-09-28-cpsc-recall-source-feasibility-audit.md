# CPSC recall source feasibility audit (pre-registration)

Status: source feasibility only. No CPSC strategy has been preregistered, no full recall archive has been acquired, no issuer coverage has been measured, and no post-announcement return has been loaded. The frozen 2021–2023 event cube contains 527 symbols and is a **coverage-limited sample, not the full US market**.

## Official publication surface

The [CPSC recalls page](https://www.cpsc.gov/Recalls) presents a `Recall Date` on each dated announcement page and states that its aggregate data are populated from those pages. It also states that the aggregate data update weekly as recalls are announced and that remedy information may change daily. A sample 2021 Peloton page exposes a recall date, recall number, named importer/distributor, units, incidents, and an explicit link to an earlier product-safety warning. These are public-announcement records rather than regulatory action dates hidden behind later disclosure processing.

CPSC's official [Recall Retrieval Web Services guide](https://www.cpsc.gov/s3fs-public/RecallRetrievalWebServicesProgrammersGuide20180917.pdf) documents `RecallDate`, `LastPublishDate`, recall number, URL, title, and manufacturer/importer/distributor collections. The guide does not define whether `LastPublishDate` is the first web-publication date, the latest content revision, or a migration/republication date, and it exposes only the current record rather than a revision history.

The official current full CSV is served from `https://www.cpsc.gov/s3fs-public/recall-data/recalls_recall_listing.csv`. A header-only range probe on 2026-09-28 returned HTTP metadata for an 18,408,016-byte S3 object with Last-Modified `2026-09-25 20:29:24 UTC`, ETag `90f891628aa5ecdb2acb3a9844599fe8-3`, and version id `tHfthjYK6txlMvybVkVa6qsk7iNMjUKc`. Its columns include recall number, date, heading, product, incidents, importer, manufacturer, and distributor, but **not** `LastPublishDate`. No full CSV was downloaded.

## Provisional point-in-time contract

The page-level recall date is plausibly the public announcement date, but the pages do not provide a time of day. The earliest defensible availability would therefore be the next frozen-sample trading session after the dated announcement. That rule is not yet approved because the current archive is mutable and the official meaning of `LastPublishDate` remains unresolved.

If official evidence confirms that `LastPublishDate` dates the current record contents, a conservative contract could use `max(RecallDate, LastPublishDate)` and exclude records whose last publication is outside the training period. If that meaning cannot be established, the line must be rejected rather than treating current text as first-vintage content.

## Issuer mapping boundary

Recall pages separately identify manufacturers, importers, distributors, and retailers. A valid cross-sectional map may use only a firm whose normalized legal name exactly matches the frozen issuer identity available before the event. Brand matches, retailer mentions, subsidiaries, parent inference, and hand-written aliases are forbidden. Multiple exact public-company firms on one recall must remain multiple exposures; unmatched recalls remain explicit misses.

This mapping rule is auditable but its usable coverage is unknown. Examples such as Peloton are not evidence that enough exact matches exist. Coverage must be checked before any outcome columns are opened.

## Current decision

- Source gate: pending `LastPublishDate` semantics and revision handling.
- Exact issuer-map design: specified, not executed.
- Full archive acquired: no.
- Training cells evaluated: 0.
- Post-announcement returns loaded: no.
- Development or consumed-period ranking: none.

Next step: seek an official definition or reproducible evidence for `LastPublishDate`, then either freeze the source as a design failure or preregister a metadata-only coverage audit with the current-object version id and hash. Do not download the full archive or inspect returns before that decision.
