# USPTO patent-grant acquisition and SEC identity correction (local fallback)

- summary: For the fixed 527-symbol 2021-2023 coverage-limited sample, the exact USPTO-authored Zenodo record 15058362 `g_patent.tsv.zip` archive was downloaded without a mirror. Its publisher MD5 is verified as `f74fbde4b2adbf980b8e4ed5394f16d2` and local SHA-256 is `46586069f04a24265f8e80e36bfa38d97ed1b703fa0e63918f001038c563e7cf`. The second declared assignee archive is still in a resumable `.part` download and has not yet been verified or promoted. The snapshot parser was corrected to use the frozen SEC `company_tickers_exchange.json` schema through the established exact parser. Explicit SEC-unmatched inventory is now persisted in `sec_unmatched.parquet` and hashed in the manifest; this retains the existing 65 missing symbols when run on the real frozen sample. Nine focused tests pass, Ruff and diff checks are clean. No returns, development/consumed data, credentials, execution state, or alternate source was used.
- stage: source-acquisition-and-identity-audit
- kpi_version: uspto-patent-grant-training-feasibility-v1
- tags: project:quant-agent-team, market:cn_a, freq:daily, market:us, freq:5min, stage:source-acquisition, strategy:uspto-patent-grant, status:in-progress
- next_step: Complete exact assignee archive download, verify publisher MD5 `6154c6d989206de65b1367b886f744d3` and local SHA-256, then build the strict snapshot and apply coverage before loading returns.

MCP memory was unavailable in this session, so this is the required local fallback to backfill when restored.
