# USPTO patent-grant design (local fallback)

- summary: Preregistered a genuinely distinct USPTO patent-grant event line for the fixed 527-symbol 2021-2023 coverage-limited sample. The current USPTO Open Data Portal now requires an account and API key, so the source contract instead uses only the immutable USPTO-authored PatentsView final metadata release at Zenodo DOI `10.5281/zenodo.15058362`, specifically the publisher-hashed raw patent and non-disambiguated assignee archives. Issuer mapping is fail-closed: exact SEC issuer titles and raw organization names under a frozen mechanical canonicalization, accepted only one-to-one, with no fuzzy match, alias, subsidiary, acronym, translation, manual override, or model-derived PatentsView identity. Public grant events start on the first sample session strictly after grant date and last five sessions. Five frozen families cover singleton, small cluster, large cluster, accelerating batch, and resumed innovation; the coverage gate requires publisher hashes, 100 issuers with at least three patents, 5,000 symbol-patent events, and all three years before the exact 400-cell 9/18 bp and delay diagnostic. No later data or execution state is authorized.
- stage: design
- kpi_version: uspto-patent-grant-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:design, strategy:uspto-patent-grant, status:preregistered
- next_step: Write the implementation plan, then sequentially acquire and verify only the two immutable publisher files; if the archive or strict mapping coverage fails, freeze the line before return evaluation.

MCP memory was unavailable in this session, so this file is the required local fallback and should be copied into MCP when that service is restored.
