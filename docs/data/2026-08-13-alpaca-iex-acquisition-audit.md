# 2026-08-13 Alpaca IEX 数据获取审计

## 结论

本机当前没有 `ALPACA_PAPER_API_KEY` 或 `ALPACA_PAPER_SECRET_KEY` 环境变量，仓库内也没有 `.env` 文件。因此未调用 Alpaca API，未获得新的 Alpaca IEX 数据，也未创建伪装成成功结果的空快照。阻塞点仅是只读市场数据凭据对当前任务进程不可见。

数据获取和发布流程已经实现，目标连续覆盖 2018-10-01 至最新已完成 XNYS 交易日。2026-04-01 后优先下载并单独隔离为未查看/盲测候选；其余按 2026Q1、2025、2024、2023、2022、2021、2020、2018Q4–2019 的顺序发布独立快照。

## 现有本地数据

只读扫描 `G:\us-intraday-lab\data\lake` 得到：

- Tiingo/IEX 1 分钟不可变快照：2025-06-23 13:30 UTC 至 2026-07-02 19:59 UTC，1,414,920 行，63 个标的，manifest 质量通过。包含 SPY、QQQ、IWM；不包含 TQQQ、SOXL 或默认行业 ETF 组。
- 本地 5 分钟快照可为部分研究提供辅助覆盖，但不是本任务要求的 Alpaca/IEX 1 分钟主数据：SPY/IWM、SPY/TQQQ、TQQQ/SOXL 等组合主要覆盖 2022–2025，少量延伸至 2026-03-30。
- 没有满足本任务标的范围的 2018 年末、2020、2021 一分钟数据；2022–2025 也没有完整的默认 16 标的一分钟覆盖。
- 2026-07-03 至 2026-08-12 在现有一分钟快照中缺失。现有快照中 2026-04-01 至 2026-07-02 的数据属于既有数据，本任务没有读取任何策略收益。

因此，现有本地数据不能被表述为完成了 2018–2026 多环境覆盖。

## 已实现流程

`scripts/acquire_alpaca_iex_history.py` 在任何下载前输出只读审计，随后仅使用 Alpaca historical market-data client：

- 固定 IEX、1Min、split adjustment；
- 默认标的为 SPY、QQQ、IWM、TQQQ、SOXL、XLB、XLC、XLE、XLF、XLI、XLK、XLP、XLRE、XLU、XLV、XLY；
- 保留响应提供的 `trade_count` 和 `vwap`；StockBarsRequest 不提供报价字段，证据中明确记录而不伪造；
- 月度请求、指数退避重试、带哈希 staging chunk 和断点续跑；
- 逐标的逐 XNYS 交易日检查 390/提前收盘实际分钟网格、重复、缺失、UTC/纽约时区、OHLCV、可选字段和异常 split-adjusted 价格；
- 缺失分钟只记录，不补值；结构或价格异常阻止发布；
- 每个市场环境发布独立、原子、内容寻址快照；已有同 ID 内容只能验证，不能覆盖；
- 盲测窗口写入 `blind_test_candidate=true`、`strategy_metrics_permitted=false`，质量证据不含策略收益。

该模块不导入 Alpaca trading client，不具备账户、broker、submit、cancel、订单或持仓操作。

## 复现命令

只读审计，不需要凭据：

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts/acquire_alpaca_iex_history.py --root G:\us-intraday-lab --available-through 2026-08-12 --audit-only
```

凭据由用户在当前进程环境中显式提供后，一次运行下载、重试、校验并发布：

```powershell
$env:ALPACA_PAPER_API_KEY = '<current read-only market-data credential>'
$env:ALPACA_PAPER_SECRET_KEY = '<current read-only market-data credential>'
$env:PYTHONPATH = "$PWD\src"
python scripts/acquire_alpaca_iex_history.py --root G:\us-intraday-lab --available-through 2026-08-12
```

## 验证

- `python -m pytest -q`：833 passed；
- `python -m ruff check .`：通过；
- `python -m mypy src/us_intraday_lab/data/alpaca_iex_acquisition.py`：通过；
- 全仓 mypy 仍有 8 个既有错误，均位于未改动的 `src/us_intraday_lab/long_horizon/orchestrator.py:676–681`。

Git 提交范围只包含 Python 源码、脚本、测试和文档；不包含 Parquet、数据库、原始数据或密钥。
