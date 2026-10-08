# Local fallback memory: SEC S-8 immutable-container boundary correction

summary: The first production SEC S-8 diagnostic attempt failed before cell evaluation because the immutable event Parquet spans 2021-01-04 through 2026-03-31 while the initial loader incorrectly required the whole container to be training-only. Repository precedent and the frozen research boundary require a training projection, not rejection of the shared immutable container. The corrected contract reads only `session_date` across the container for boundary audit, applies Parquet date filters before loading outcome columns, records excluded row count, and rejects any evaluated row outside 2021-2023. Signal definitions, event states, 400 cells, costs, delay, retention gates, and terminal rules are unchanged.

stage: sec-s8-training-boundary-debug

kpi_version: versionless-training-feasibility

tags: project:quant-agent-team, market:cn_a, freq:daily, stage:debug, strategy:sec-original-s8, status:root-cause-fixed

next_step: Re-run the full targeted tests and Ruff, then rerun the immutable-hash production diagnostic. If it completes, preserve its exact terminal decision. If another invariant fails, investigate before changing anything and do not weaken the economic design or load development/consumed data.
