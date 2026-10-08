# SEC S-3ASR training feasibility implementation plan

## Goal

Implement and execute the frozen exact-original S-3ASR five-session,
400-cell, training-only diagnostic without changing existing S-8 evidence or
opening any development, consumed, primary-document, monitoring, or execution
state.

## Tasks

1. Add failing unit tests for the S-3ASR coverage hash/form contract, exact
   400-cell identity, five-session activity, 252/63-session causal repetition,
   opposite continuation/reversal ordering, cost/delay contract, training-only
   projection from the wider immutable container, missing-price failure, and
   terminal no-execution output.
2. Implement `sec_s3asr_training_feasibility.py` as an independent diagnostic
   so the frozen S-8 implementation and result cannot be rewritten. Reuse only
   pure tested metric/portfolio behavior where identity and error namespaces
   remain S-3ASR-specific.
3. Add an atomic command-line runner with fixed immutable hashes and immutable
   JSON, Markdown, and external Parquet cell-table outputs.
4. Run focused unit tests and Ruff, then the broader relevant diagnostic tests.
5. Execute all 400 cells once against the frozen 2021-2023 outcomes, inspect
   status/cardinality/missingness/retention, freeze the result, write local
   fallback memory, and commit/push tracked code and summaries while leaving
   `state/` and the external cell table untracked.

## Stop rules

- Any source-hash, coverage, schema, time-boundary, duplicate, grid-cardinality,
  or selected-price violation fails closed.
- If fewer than two families retain valid cells, freeze and abandon S-3ASR;
  do not tune its event life, thresholds, families, grid, or identity after
  seeing outcomes.
- If training passes, stop at a recommendation for a separately designed
  development-data acquisition. Do not load development or consumed periods.
- Never create a strategy version, touch Paper/monitoring pools, call a broker,
  submit/cancel an order, alter routing, or shut down services.
