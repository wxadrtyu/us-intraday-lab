---
type: data-decision
summary: Treasury DTS has 752 dated 2021-2023 report dates and official following-business-day 4pm publication semantics; dated PDFs exist, but historical first-byte vintage and broad-XLF causal exposure require further design verification. No preregistration, bulk download, or outcome ranking.
stage: source-feasibility
kpi_version: dts-fiscal-liquidity-design-v0
tags:
  - project:quant-agent-team
  - market:cn_a
  - freq:daily
  - stage:source-feasibility
  - strategy:dts-fiscal-liquidity-design-v0
  - status:pending-source-and-mapping
next_step: Verify official revision/version behavior and XLF historical map; reject if point-in-time first prints cannot be defended, otherwise preregister before training acquisition.
---

Frozen 2021-2023 527-symbol event-cube sample is coverage-limited, not full market. Eight official dated DTS PDFs were probed in memory only. Their embedded creation dates align with next-business-day publication, but later S3 modification times in 2021/early 2022 do not establish immutable first-print bytes. KRE has zero bar-5 sample dates in 2021; XLF has 221/230/180 finite dates in 2021/2022/2023, but is not a pure bank proxy. No post-release return or 400-cell diagnostic was loaded. MCP memory search/create are unavailable, so this tagged local fallback needs backfill.
