# DOL weekly claims official source parser checkpoint

- summary: Added official DOL OUI annual archive parser and a two-stage, at-most-one-request-per-second collector. It validates exact dated PDF links from 2021/2022/2023 annual POST responses, demands 52 per year and 156 unique total, freezes raw HTML and manifest hashes before any PDF fetch, and later permits only those exact URLs with raw-byte hash replay protection. This is code-only; no 2021-2023 PDF or return data was loaded.
- stage: source-parser-implementation
- kpi_version: none; versionless training feasibility
- type: data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:dol-ui-claims, status:source-parser-tested
- validation: Five focused tests passed and Ruff clean. Tests cover exact official link/date parsing, duplicate/cross-year failure, 52/52/52 source freeze, changed hash, and refusal to fetch PDFs before manifest.
- next_step: Sequentially capture and hash the three official annual HTML responses, publish their manifest hash, then and only then acquire 156 exact linked PDFs.
