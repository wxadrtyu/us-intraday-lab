# USPTO Patent-Grant Event: coverage-gate rejection

This is the frozen 2021–2023 training sample of 527 symbols from the event cube, a **coverage-limited sample, not the full market**. The two exact USPTO-authored Zenodo record 15058362 archives match their publisher MD5 values. Their local SHA-256 values, the event-cube and SEC identity hashes, and the external snapshot hashes are in the adjacent JSON evidence.

The strict SEC-title-to-raw-assignee-name mapping retained 65 pre-existing SEC-unmatched symbols and rejected every ambiguous or unmatched raw organization name without fuzzy matching. It produced 45 exact issuer mappings, but only 15 issuers had training-period qualifying grants. Just 5 issuers had at least three grants versus the frozen 100-issuer gate; 521 symbol-patent events fell far below the 5,000-event gate. Qualifying events span 2021, 2022, and 2023, but the two numeric coverage failures are decisive.

Decision: `ABANDON_USPTO_PATENT_GRANT_COVERAGE_GATE`. The 400-cell return grid was **not run**; zero cells were evaluated, so there is no performance claim. This family is frozen with no local mapping relaxation, tuning, development/consumed-period ranking, version creation, Paper activation, or order routing. The next research line must use a genuinely different free, auditable point-in-time source.
