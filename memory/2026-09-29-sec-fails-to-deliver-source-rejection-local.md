# Local fallback memory: SEC fails-to-deliver data

summary: SEC 2021-2023 Fails-to-Deliver Data was rejected at the public-availability and historical-version gates. The official archive has two files per month and documents an approximate schedule, but SEC explicitly cannot guarantee posting by a particular date. It provides no per-file first-publication timestamp, immutable first-release hash manifest, or complete correction/replacement ledger. Month-end or next-month-15th availability would be invented and potentially look-ahead. No file was acquired, no event threshold or symbol mapping was performed, the event cube was not opened, no outcome was read, and cells_completed is zero.

stage: source-public-availability-gate

kpi_version: versionless-sec-ftd-source-screen

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:source-public-availability-gate, strategy:sec-ftd, status:rejected, source:sec, sample:coverage-limited-527

next_step: Audit USAspending 2021-2023 federal contract award transactions as a genuinely different official procurement event source. First prove the relation among action_date, submitted/modified timestamps, and actual public availability; confirm stable transaction and award identifiers, historical versions, corrections, cancellations, and immutable or reconstructable first-public states. Predefine one economically homogeneous new-obligation contract-action family and do not mix grants, loans, modifications, deobligations, IDV ceilings, subcontract data, or agency announcements for volume. Before any outcome read, count the metadata-only universe and evaluate coverage using only the recipient's complete legal business name mechanically identical to a frozen SEC issuer. Prohibit UEI/DUNS-to-parent inference, products, agencies, subsidiaries, parents, former names, abbreviations, fuzzy matches, and manual aliases. Freeze and switch if point-time publication, versioning, event semantics, event volume, or exact-name coverage cannot be proven.

## Frozen evidence

The archive nominally contains 72 semi-monthly 2021-2023 files, but official publication timing is only approximate and expressly not guaranteed. `ABANDON_SEC_FTD_PUBLIC_AVAILABILITY_GATE`; `semi_monthly_files_acquired=false`; `point_in_time_symbol_mapping_performed=false`; `cells_completed=0`; `post_availability_outcomes_loaded=false`. MCP memory search/create remained unavailable, so this tagged local fallback needs later backfill.
