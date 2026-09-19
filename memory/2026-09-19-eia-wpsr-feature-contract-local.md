# EIA WPSR causal feature contract checkpoint

- summary: Added training-only release-state and per-symbol prior-XLE-beta feature construction for the coverage-limited 527-symbol research sample. It uses strictly prior 12 complete release Differences and 60 paired, finite bar-5 opening-return sessions strictly before the first sample session after publication. XLE is a reference only; duplicate bar-5 keys are invalidated and counted, not imputed or double-counted. Missing pairs and nonpositive beta remain explicit exclusions. No EIA CSV or post-release return diagnostic was consumed at this checkpoint.
- stage: causal-feature-implementation
- kpi_version: none; versionless training feasibility
- type: data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:eia-wpsr-supply-shock, status:feature-contract-tested
- validation: Four focused feature tests passed; Ruff clean. Tests cover next-session availability, strict prior rolling median, prior 60 paired bar-5 beta, excluded reference/negative beta, tie order, and later-period exclusion.
- next_step: Finish the source-manifest acquisition already in progress, then add the external snapshot build script and hard coverage gate before any outcome loading.
