# EIA WPSR verified snapshot builder checkpoint

- summary: Added a frozen-source-only CSV acquisition path so the 154 official issue pages and live archive index are not re-fetched during Table 4 download. Added a read-only snapshot verifier requiring exact release order, per-file CSV SHA-256 and schema; a training cube reader verifies its SHA-256 and pushes down the 2021-2023 date filter before reading feature values. Added an external-only feature builder that requires exactly the frozen 527 symbols and XLE. CSV acquisition is still in progress, so this stage makes no coverage or return claim.
- stage: verified-snapshot-builder-implementation
- kpi_version: none; versionless training feasibility
- type: data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:eia-wpsr-supply-shock, status:csv-acquisition-in-progress
- validation: 15 focused tests passed; Ruff clean; no development/consumed period loaded for ranking and no return cell run.
- next_step: Wait for existing single CSV downloader to complete, verify 154/154 bytes and source hashes, build frozen features, then run the preregistered coverage gate before loading post-availability returns.
