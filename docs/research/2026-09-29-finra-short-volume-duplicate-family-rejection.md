# FINRA daily short-volume duplicate-family rejection

Decision: **ABANDON_FINRA_SHORT_VOLUME_DUPLICATE_FAMILY**. The proposed 2021-2023 FINRA Reg SHO Daily Short Sale Volume line is not a genuinely new source and will not be reopened. The exact Consolidated NMS family was already source-audited, acquired, causally aligned, coverage-gated, and evaluated under a frozen 400-cell training diagnostic on 2026-09-17. This turn did not acquire data, open the event cube, or read a new return series.

## Existing frozen evidence

FINRA's official source contract is usable: Consolidated NMS daily files aggregate publicly disseminated off-exchange NMS trades reported to the TRFs and ADF; FINRA says files are posted by 18:00 ET on the trade date and that rare later updates are listed alongside originals and marked `Updated`. Historical files are available from August 2018. Those facts were already incorporated into the frozen design at `docs/superpowers/specs/2026-09-16-finra-short-volume-training-design.md`.

The completed tracked evidence is conclusive for this source family:

- `research/results/2026-09-17-finra-short-volume-training-coverage.md`: coverage gate PASS; 381,084 of 388,745 event rows covered across 743 sessions in 2021-2023.
- `research/results/2026-09-17-finra-short-volume-listing-audit.md`: 753 files audited; 14 distinct official page hashes; availability and listing exceptions recorded.
- `research/results/2026-09-17-finra-short-volume-training-feasibility-summary.md`: all 400 frozen cells completed, zero retained cells, no retained families, and decision `ABANDON_FINRA_SHORT_VOLUME_NO_VERSION_CREATED`.

Changing facility pooling, event thresholds, rolling windows, missingness rules, or symbol treatment after that zero-pass result would be local retuning of an exhausted family. The official warning that daily short-sale volume is off-exchange flow rather than short interest also remains binding; relabeling it as issuer bearish positioning does not create a new causal source.

Official sources:

- https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files
- https://www.finra.org/finra-data/browse-catalog/short-sale-volume
- https://www.finra.org/rules-guidance/notices/information-notice-051019
- https://www.finra.org/sites/default/files/DailyShortSaleVolumeFileLayout.pdf

Final state for this attempted continuation: `genuinely_distinct_source=false`, `new_preregistration_created=false`, `new_source_files_acquired=false`, `new_symbol_mapping_performed=false`, `event_cube_opened_this_turn=false`, `new_cells_completed=0`, `new_post_availability_outcomes_loaded=false`. The historical frozen line remains `cells_completed=400`, `retained_cells=0`, `strategy_versions_created=0`. No development or consumed period, Paper state, monitoring pool, broker path, order route, or shutdown action was touched.
