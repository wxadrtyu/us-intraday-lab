# EIA WPSR official archive source parser stage

- summary: Added a fail-closed parser for exact official 2021-2023 WPSR issue links, stated issue dates, same-issue Table 4 CSV links and four exact `Difference` rows. Acquisition separates source-manifest freezing from CSV retrieval; it preserves raw bytes, SHA-256, HTTP metadata and retrieval time, rejects changed re-fetches, and limits the CLI to at most one request per second. No 2021-2023 CSV or outcome was retrieved in this stage.
- stage: source-parser-implementation
- kpi_version: none; versionless training feasibility
- type: data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:eia-wpsr-supply-shock, status:source-parser-tested
- validation: Seven focused tests passed; Ruff and diff check clean. Tests use local fixture bytes and do not inspect training outcomes.
- next_step: Sequentially acquire official 2021-2023 archive index and each dated issue page into external staging, freeze the complete source manifest, then retrieve linked Table 4 CSVs only; preserve failures and hashes.
