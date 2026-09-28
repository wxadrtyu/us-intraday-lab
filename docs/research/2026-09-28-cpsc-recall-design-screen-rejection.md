# CPSC recall design-screen rejection

Decision: **ABANDON_CPSC_RECALL_SOURCE**. The line is frozen before preregistration, full archive acquisition, issuer matching, coverage measurement, or any post-announcement return read. The frozen 2021–2023 event cube contains 527 symbols and is a **coverage-limited sample, not the full US market**.

## Publication-version gate

CPSC recall pages identify a recall date and recall number, but do not expose a publication time or a visible revision timestamp. A next-session rule could handle the missing time of day, but it cannot establish which title, firm-role fields, incident counts, or other contents were visible on that date.

CPSC explicitly states that aggregate recall data update weekly and remedy data may change daily. Its official API guides from 2016, 2017, and 2018 list both `RecallDate` and `LastPublishDate`, but none defines `LastPublishDate` as a first-publication timestamp or as a complete content-version timestamp. The service exposes the current record and no revision ledger.

The current full CSV is a versioned S3 object, so today's download could be hashed and reproduced by its current version id. That does not recover the object or record contents available in 2021–2023. The CSV also omits `LastPublishDate`. Searching official CPSC documentation produced field listings and examples but no semantics or historical version-recovery mechanism.

## Issuer-map consequence

The proposed exact legal-name rule depends on current manufacturer/importer/distributor text. Without historical versions, assigning that current text to `RecallDate` can leak later edits. Moving every record to an undefined `LastPublishDate` would merely replace one unsupported timing assumption with another. Recall number and date alone cannot identify the affected listed issuer.

## Frozen outcome

- Historical first-publication/content-version gate: fail.
- Strict point-in-time issuer map: unavailable.
- Full archive acquired: no.
- Issuer matches or coverage evaluated: 0.
- Training cells evaluated: 0.
- Post-announcement returns loaded: no.
- Reopening by inferred delay, current text, or hand-built aliases: forbidden.

This rejection applies to the CPSC current-page/current-API/current-CSV contract. It does not claim that product recalls lack market impact. Research now moves to a genuinely different official dated-release family; its public event date and exact legal entity must be established before metadata acquisition or outcomes.
