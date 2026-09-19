# EIA WPSR training coverage rejection

- summary: All 154 official 2021-2023 EIA WPSR Table 4 CSVs and 154 dated pages passed raw SHA-256 and exact schema checks. The frozen 527-symbol sample is coverage-limited, not full market. Only 77 release-availability sessions had at least 150 positive, prior-60-pair bar-5/XLE-beta symbols versus the preregistered 100; the line was abandoned at coverage with zero of 400 return cells run. Other floors passed: 263 unique eligible symbols, 20,084 eligible pairs, 52/51/51 releases and all family activation floors. No threshold/mapping tuning, later-period ranking or execution followed.
- stage: terminal-coverage-rejection
- kpi_version: none; versionless training feasibility
- type: failed-experiment; review-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:eia-wpsr-supply-shock, status:frozen-no-candidate
- evidence: research/results/2026-09-19-eia-wpsr-supply-shock-training-feasibility-summary.json; source manifest SHA-256 7d64803e26acd2ea1e2db1c05c466280155e30d7a235e9220528bd22ba6b9690; CSV manifest SHA-256 6a9275fb566387077ef5b590b358d985332bda06ef66dfcd1521792ec2288b05; feature manifest SHA-256 70ca5e4269d4e44c2cbeb116bc3afddffbfca50ad4946aa44390f9e929b279e7.
- next_step: Do not reopen EIA or tune the gate. Investigate a genuinely different free, official point-in-time return source and preregister it before training-data acquisition. No Paper, broker, pool or shutdown action.
