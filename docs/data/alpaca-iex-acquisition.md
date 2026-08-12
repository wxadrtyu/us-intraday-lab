# Alpaca IEX 日内数据获取与不可变快照

## 目的与范围

此任务以零新增数据费用补齐只做多美股日内研究数据。默认连续覆盖 2018-10-01 至当前已完成 XNYS 交易日，包含：2018 年末快速下跌、2020 年疫情暴跌与反弹、2021 年强趋势、2022 年熊市、2023–2025 年不同波动环境和 2026 年当前环境。

下载按以下优先级执行：

1. 2026-04-01 至当前可得日期，标记为未查看/盲测候选；
2. 2026Q1、2025、2024、2023，各环境独立快照；
3. 2022、2021、2020；
4. 2018-10-01 至 2019-12-31，保留阶段过渡而不制造空档。

默认标的是 SPY、QQQ、IWM、TQQQ、SOXL，以及 XLB、XLC、XLE、XLF、XLI、XLK、XLP、XLRE、XLU、XLV、XLY。

## 安全边界

代码只构造 `alpaca.data.historical.StockHistoricalDataClient` 和 `StockBarsRequest`。不导入交易客户端，不查询账户、订单或持仓，不具备 broker、submit、cancel 能力。凭据只能由当前运行环境中的 `ALPACA_PAPER_API_KEY` 和 `ALPACA_PAPER_SECRET_KEY` 提供；脚本不会读取仓库文件或聊天历史中的密钥。

请求固定为 Alpaca IEX、1 分钟、split adjustment。保留 API bar 响应中的 `trade_count` 和 `vwap`；StockBarsRequest 不返回报价字段，因此证据中明确记录报价字段未提供，不伪造或推导报价。

## 质量与盲测规范

每个优先窗口单独发布到 `data/lake/acquired/alpaca-iex-1min-<hash>/`。目录名由内容、范围、标的、feed、复权和日历元数据共同寻址；重复运行只接受完全相同的已有快照，不能覆盖。

校验逐 XNYS 常规交易时段计算预期分钟、实际分钟与缺失分钟。任何重复、非有限值、非法 OHLCV、超过阈值的 split-adjusted 跨 bar 跳变或分钟内异常价格范围都会阻止发布。IEX 没有成交的分钟保持缺失，只报告，不补值。快照保留 `quality-evidence.json` 的逐标的逐交易日覆盖记录。

2026-04-01 之后的窗口在 manifest/evidence 中标记 `blind_test_candidate=true` 和 `strategy_metrics_permitted=false`。本任务只允许读取其覆盖和质量字段，不允许运行或查看策略收益。

## 复现

```powershell
$env:ALPACA_PAPER_API_KEY = '<read-only market-data credential>'
$env:ALPACA_PAPER_SECRET_KEY = '<read-only market-data credential>'
python scripts/acquire_alpaca_iex_history.py --root G:\us-intraday-lab
```

脚本在任何下载前先输出只读审计（只报告凭据是否存在，不报告值）。可先运行 `--audit-only`。可用 `--available-through YYYY-MM-DD` 固定可复现的数据截止日，或用 `--symbols` 显式缩小/扩展标的。每月请求先写入带哈希的 staging chunk，失败重跑时复用已验证 chunk，再一次性校验并发布窗口快照。原始 Parquet、数据库和密钥都被 `.gitignore` 排除，不应提交。
