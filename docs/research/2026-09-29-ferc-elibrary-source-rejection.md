# FERC eLibrary Electric Issuance/Order source rejection

## Decision

Freeze this line as `ABANDON_FERC_ELIBRARY_POINT_IN_TIME_SOURCE_GATE`. The official eLibrary metadata proves when a record is posted, but the current service does not prove that the native file bytes and descriptive metadata now returned for a 2021-2023 accession are the bytes and metadata first published at that historical `Posted` timestamp. No source preregistration, issuer mapping, event-cube outcome access, or return-grid work is permitted for this line.

This decision applies only to the frozen 2021-2023 sample of 527 symbols. That sample is coverage-limited and is not the full US equity market.

## Official semantics that passed

- FERC's official eLibrary help defines `Posted` as the date a document is published in eLibrary. Document Info exposes the precise Posted time, accession number, Official flag, document date, first-received time, category, library, class/type, dockets, and Role/Org rows.
- A direct official API probe reproduced accession `20260113-5151`, including its accession, Posted date, document identifiers, native transmittal file identifiers, file names, sizes, dockets, and Role/Org metadata.
- The official class/type vocabulary supports the ex-ante Electric / Issuance / `Order/Opinion` / `Delegated Order` screen. A 2021 Posted-date probe returned 2,798 records. A description-only exact-phrase probe for `"Letter order accepting"` returned 2,320/2,265/2,223 records in 2021/2022/2023, so gross event count is not the source gate's failure.
- Errata are often represented as later, separate accessions that cite the original order. The audit observed 24/30/47 delegated-order description hits for `corrected` in 2021/2022/2023, including explicit later errata accessions. This is useful correction evidence but is not a complete version ledger for every native component.

## Decisive point-in-time failure

The public API returns current accession metadata and current native-file identifiers, but neither official help nor the API exposes a historical component manifest, original component hash, component creation/first-publication timestamp, replacement timestamp, or superseded-byte archive. A stable accession number identifies a record; it does not by itself prove that every currently downloadable component and current description remained byte-for-byte unchanged since the original Posted time.

The official `Generate PDF` control is explicitly an on-demand rendition that combines current components. It is not an admissible historical artifact. Downloading and hashing current native files would freeze today's state only and could not reconstruct the 2021-2023 first-published state. Separate errata accessions do not establish that all corrections or administrative replacements always preserve the prior component bytes under a separately queryable accession.

Because the proposed event family and strict issuer mapping would depend on the order text or current descriptive metadata, the missing historical component/version contract is decisive before coverage. Do not use current native bytes, generated PDFs, current descriptions, file IDs, HTTP headers, inferred delay, or observed errata behavior as a substitute for historical first-publication evidence.

## Frozen consequences

- Do not acquire the 2021-2023 order corpus or perform Role/Org, caption, description, parent/subsidiary, or alias mapping.
- Do not rescue the line by treating all delegated orders as economically homogeneous, mixing rate/tariff acceptance with accounting, merger, notice, procedural, compliance, or errata orders, or selecting a description pattern after coverage is observed.
- Do not load post-availability outcomes or run any of the fixed 400 cells.

Final state: `source_point_in_time=false`, `preregistered=false`, `full_index_acquired=false`, `native_component_inventory_acquired=false`, `issuer_mapping_performed=false`, `event_cube_opened=false`, `cells_completed=0`, `post_availability_outcomes_loaded=false`. No development or consumed period, strategy version, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
