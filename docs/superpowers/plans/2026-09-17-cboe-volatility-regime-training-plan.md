# Cboe volatility-regime training feasibility plan

1. Add a tested read-only acquisition module that downloads the six official Cboe CSVs, validates schemas and dates, discards all non-training rows before persistence, records source hashes, and writes an immutable external snapshot atomically.
2. Add a tested feature builder that computes lagged levels, changes, ratios, and rolling z-scores and joins each event only to the most recent strictly earlier Cboe date without multi-session filling.
3. Add a tested diagnostic that enumerates exactly 400 preregistered cells, applies 9 bp, 18 bp, and delayed-entry accounting, and enforces the frozen retention gates.
4. Run acquisition and coverage checks. Stop closed on duplicate dates, malformed schemas, incomplete 2021-2023 coverage, hash mismatch, or any later-period row in the persisted snapshot.
5. Run the training-only diagnostic against the frozen event hash, write atomic JSON/Markdown and external Parquet artifacts, and verify `status=COMPLETE` plus `cells_completed=400`.
6. If fewer than two families retain cells, freeze the failed experiment, create no strategy version, and do not load development or consumed data. If two or more families retain cells, stop at an acquisition recommendation; do not acquire development data in the same step.
7. Run focused tests, the data/research suite, Ruff, and the full suite; distinguish pre-existing failures from regressions. Save the required local fallback memory because MCP memory is unavailable.
