# Polygon Historical Security Master Design

## Objective

Build an independent, point-in-time US-stock security master from Polygon reference data for every calendar month from January 2018 through March 2026. The dataset must preserve delisted and missing records, provide immutable provenance, resume safely after interruption, and produce machine-verifiable evidence before it can clear the existing `INDEPENDENT_HISTORICAL_MASTER_MISSING` gate.

This work is data validation only. It must not add broker, order, submit, cancel, Paper activation, or strategy-ranking behavior.

## Frozen requirements

- Provider: Polygon REST `GET /v3/reference/tickers`.
- Query scope: `market=stocks`, `locale=us`, each requested as-of date, and both `active=true` and `active=false`.
- Range: month-end as-of dates from `2018-01-31` through `2026-03-31`.
- Page size and order: `limit=1000`, `sort=ticker`, `order=asc`.
- Credential: `POLYGON_API_KEY` read from the environment and never written to URLs, manifests, logs, exceptions, or output files.
- Raw provider responses are immutable evidence. Canonical monthly snapshots are derived artifacts and never replace raw pages.
- Missing provider fields remain null. No forward fill, status inference, symbol substitution, provider splicing, or cash/zero-return interpretation is allowed.
- Existing Alpaca source files and monthly-universe decisions remain immutable.

## Considered approaches

### 1. Polygon SDK

The SDK reduces HTTP boilerplate, but adds a dependency and can obscure exact request, pagination, and retry behavior. That weakens the evidence chain and makes credential-redaction guarantees harder to audit.

### 2. Canonical snapshots only

Writing one Parquet file per month is compact, but discards the original page boundaries, request IDs, and provider payloads. A later validator could not distinguish provider evidence from locally reconstructed data.

### 3. Raw pages plus canonical snapshots (selected)

Use the Python standard library for read-only HTTPS calls. Store each page body, a redacted request identity, content hash, response request ID, and retrieval timestamp. After all pages for both activity states exist, normalize them into one deterministic monthly Parquet snapshot and validate it independently. This is slightly more storage and code, but it preserves provenance and supports exact resume.

## Architecture

### Acquisition module

`src/us_intraday_lab/data/polygon_historical_master.py` owns:

- deterministic month-end generation;
- a read-only Polygon client created from `POLYGON_API_KEY`;
- URL validation that permits only HTTPS requests to `api.polygon.io` and the `/v3/reference/tickers` path;
- sequential pagination for both activity states;
- conservative request pacing and bounded exponential backoff for HTTP 429 and transient 5xx failures;
- atomic publication of raw JSON pages and page manifests;
- resume validation by request-identity and content hashes;
- canonical, sorted, typed monthly Parquet snapshots;
- full-source validation independent of acquisition state.

The module exposes dependency-injected transport and sleep functions so unit tests use real parsing and retry logic without external requests.

### Command-line scripts

`scripts/acquire_polygon_historical_master.py` runs acquisition for a requested month range. It prints only counts and paths, never response bodies or credentials.

`scripts/audit_polygon_historical_master.py` validates the full expected grid and writes immutable JSON and Markdown evidence. It also compares the Polygon master with the existing Alpaca candidate asset snapshot and monthly decisions, reporting exact unmatched symbols without treating symbol disagreement as missing market data.

### Storage layout

Under the external data root:

```text
data/staging/polygon_reference_tickers_v1/
  raw/asof=YYYY-MM-DD/active=true/page-NNNNN-<request-hash>.json
  raw/asof=YYYY-MM-DD/active=true/page-NNNNN-<request-hash>.manifest.json
  raw/asof=YYYY-MM-DD/active=false/page-NNNNN-<request-hash>.json
  raw/asof=YYYY-MM-DD/active=false/page-NNNNN-<request-hash>.manifest.json
  snapshots/asof=YYYY-MM-DD/tickers.parquet
  snapshots/asof=YYYY-MM-DD/manifest.json
```

Raw page manifests contain the redacted request parameters, request identity hash, response content hash, provider request ID, result count, page number, retrieval time, and next-page presence. They never contain the API key or an authenticated URL.

Canonical rows retain `ticker`, `name`, `market`, `locale`, `primary_exchange`, `type`, `active`, `currency_name`, `cik`, `composite_figi`, `share_class_figi`, `delisted_utc`, `last_updated_utc`, `asof`, and `provider`. Optional absent fields remain null.

## Data flow and resume behavior

For each month and activity state, the downloader starts from the deterministic first request. Before publishing a page it validates the response status, result schema, sort order, page identity, and next URL. It writes the raw body to a temporary sibling, atomically renames it, then does the same for the manifest.

On resume, a page is reused only when both files exist, their hashes agree, and their redacted request identity matches the expected page. A one-sided pair, hash mismatch, changed next URL, duplicate ticker within an activity state, or credential-bearing URL fails closed and requires an audit; it is never silently overwritten.

After both activity states finish, the builder parses all raw pages, rejects duplicate `(ticker, active)` records, sorts deterministically by ticker and activity state, writes the monthly snapshot atomically, and records a content hash and the ordered raw-page hashes in its manifest.

## Independent validation and gate semantics

Validation reconstructs the expected 99 month-end dates and both activity states from configuration rather than trusting a completion flag. It verifies:

- every raw page has a matching manifest and no temporary files exist;
- request identities, response hashes, page chains, provider request IDs, and canonical hashes agree;
- every record is a US stock and its returned `active` value matches the query state;
- ticker order and page progression are deterministic, with no duplicate records;
- all 99 monthly snapshots are present and derivable from their exact raw pages;
- the Polygon master has non-empty coverage for every month;
- comparison outputs preserve every unmatched Alpaca or decision symbol explicitly.

Only the validator's immutable report may set `historical_master_validated=true` in the existing SIP audits. A caller-provided boolean, existence check, or acquisition completion message remains insufficient. The existing coverage floor, source checks, and no-splicing rules continue to apply.

## Error handling

- Missing credential: stop before any network request.
- HTTP 401/403: stop immediately as an entitlement or credential failure.
- HTTP 429/5xx or transport interruption: bounded retries with conservative delay; if exhausted, leave no partial published pair and exit nonzero so the next run can resume.
- Invalid JSON, provider status other than `OK`, unexpected host/path in `next_url`, or schema/status mismatch: stop and preserve already published evidence.
- Existing immutable collision: reuse only if all hashes and identities match; otherwise fail without modification.
- Empty monthly result or missing activity-state chain: validator rejects the dataset.

## Testing and verification

Implementation follows test-first development. Unit tests cover credential isolation, normalization, pagination, URL constraints, retry decisions, atomic resume, collision rejection, manifest hashing, month-end generation, canonical derivation, and independent validation. Script tests cover immutable report output and prove that self-attestation cannot clear the gate.

Before completion, run targeted tests and Ruff on every changed Python file, then the complete test suite. A small live pilot uses one historical month and both activity states; its raw and canonical artifacts must pass the same validator before the full 99-month acquisition starts.

## Out of scope

- Rebuilding or rewriting the Alpaca monthly universe.
- Inferring exact listings between monthly as-of dates.
- Strategy evaluation, parameter selection, Paper activation, or order routing.
- Adding other reference-data providers or splicing Polygon with Alpaca.
