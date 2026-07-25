# 2026-07-26 独立工程初始化阶段记忆

- memory_type: `data-decision`
- summary: 新建独立 Git 工程 `G:\us-intraday-lab`，用于美股分钟级策略研究，避免与 `G:\quant-agent-team-us` 的既有中频、日频策略、数据库和监控池混合。
- stage: `project-bootstrap`
- kpi_version: `not-set`
- tags:
  - `project:us-intraday-lab`
  - `market:us`
  - `freq:intraday`
  - `stage:project-bootstrap`
  - `status:completed`
- constraints:
  - 初始阶段仅允许方案设计、回测和模拟盘。
  - 未经人工审核，不允许真实资金下单。
  - 与原工程之间默认零运行时依赖。
- next_step: 确认首版范围，比较数据与交易架构路线，形成正式设计文档。
- memory_backend_status: `codex-mcp-memory unavailable in current tool context; local fallback used`
