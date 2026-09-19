# DOL weekly UI claims distinct-source assessment

- summary: After EIA coverage rejection, identified official DOL Office of Unemployment Insurance archived weekly news-release PDFs as a distinct labor-demand source. Official 2021/2022/2023 year indexes each list 52 release-specific PDFs; representative links return PDF 200. A 2020 pretraining PDF shows explicit 8:30 ET embargo and first-page advance claims figures. No 2021-2023 PDF or training outcome was downloaded or ranked during assessment. A read-only frozen-cube structure audit found 116/152 Friday proxies with at least 150 non-SPY symbols having 60 bar-5 SPY-paired observations strictly before Thursday; this is not actual release-calendar coverage.
- stage: source-assessment
- kpi_version: none; versionless training feasibility
- type: market-research; data-decision
- tags: project:quant-agent-team, market:cn_a, freq:daily, strategy:dol-ui-claims, status:source-assessed-not-preregistered
- next_step: Preregister source bytes, PDF extraction, strict causal availability, SPY exposure, frozen families/coverage and cost-delay gates before sequential 2021-2023 PDF acquisition. If timestamped original releases or extraction cannot be audited, freeze at design/source stage.
