# Local fallback memory: SEC original Form S-8 training rejection

summary: The frozen exact-original SEC Form S-8 diagnostic completed all 400 preregistered 2021-2023 training cells with zero invalid cells and retained zero cells across zero families. The terminal decision is `ABANDON_SEC_S8_NO_VERSION_CREATED`. The immutable event cube contributed 388,745 training rows across 753 sessions after metadata-only exclusion of 411,054 container rows outside training; 482 admissible issuer-document pairs expanded to 1,275 active symbol-session states. The full external cell table SHA-256 is `e23ee4126686d3deef31529cbe9b01b049681d9093757b16a7edd15a03737a81`. No primary-document body, development/consumed data, strategy version, Paper state, monitoring pool, broker path, or order route was opened or changed.

stage: sec-s8-training-result

kpi_version: versionless-training-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:training-result, strategy:sec-original-s8, status:failed-experiment

next_step: Freeze the SEC original Form S-8 family without tuning event life, family definitions, windows, grid, costs, delay, or retention gates. Move to a genuinely distinct issuer-direct official event family and repeat source semantics, immutable timing/identity, metadata-only coverage, design, and training gates. Continue to keep development and consumed periods closed until a training family passes; do not create a strategy version or touch Paper/execution state.

Frozen result: `status=COMPLETE`; `decision=ABANDON_SEC_S8_NO_VERSION_CREATED`; `cells_completed=400`; `invalid_cells=0`; `retained_cells=0`; `retained_families=0`; `training_event_rows=388745`; `calendar_sessions=753`; `active_state_rows=1275`; `container_rows_excluded_outside_training=411054`; `event_cube_sha256=399020c0abbdd554e4f4652593debcf33a2090bcc684c5d78bc1e27da92889a9`; `coverage_sha256=62943eb65d564e07960efcd206563adf1baebd5715d0c2db30a56cbe15be2ca8`; `cells_sha256=e23ee4126686d3deef31529cbe9b01b049681d9093757b16a7edd15a03737a81`; `strategy_versions_created=0`; `development_or_consumed_loaded=false`; `primary_document_bodies_opened=false`; `paper_activation=false`; `order_route=FORBIDDEN`. MCP memory search/create remained unavailable, so this tagged local fallback requires later backfill.
