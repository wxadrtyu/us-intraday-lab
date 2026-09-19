# USPTO patent-grant snapshot builder (local fallback)

- summary: Implemented and verified the fail-closed USPTO PatentsView snapshot builder for the fixed 527-symbol 2021-2023 coverage-limited sample. It streams the two declared ZIP/TSV archives, verifies publisher MD5 plus local SHA-256 without loading archive bytes into memory, applies the frozen mechanical organization canonicalization, accepts only one-to-one raw assignee and SEC issuer-title keys, preserves ambiguity/unmatched reasons, joins only exact patent IDs, filters only after source validation, and atomically publishes snapshot, issuer map, rejections, and manifest. Seven focused tests pass, Ruff is clean, and diff checks pass. The public Zenodo file endpoint returned repeated 504/timeouts with zero bytes during this stage, so no source was substituted and acquisition remains pending under the preregistered retry/freeze rule. No development/consumed data, credentials, API key, or execution state was touched.
- stage: snapshot-builder
- kpi_version: uspto-patent-grant-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:snapshot-builder, strategy:uspto-patent-grant, status:implemented
- next_step: Retry the exact immutable Zenodo file endpoint without substitutes; if retrieval succeeds verify publisher hashes and run the strict coverage snapshot, otherwise freeze the repeated acquisition failure after the bounded retry audit and move to a different official point-in-time source.

MCP memory was unavailable in this session, so this file is the required local fallback and should be copied into MCP when that service is restored.
