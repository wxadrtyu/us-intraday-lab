# 2026-08-13 一分钟数据获取完成报告

## 结论

本次已在 `G:\us-intraday-lab` 发布 2018-10-01 至 2026-08-12 的分源、不可变、内容寻址一分钟快照。默认范围为 SPY、QQQ、IWM、TQQQ、SOXL 和 11 个主要行业 ETF，共 16 个标的。

Alpaca Basic/IEX 对本凭据实际只从 2020-07-27 开始返回数据，因此 2018-10 至 2020-12 另以仓库已经采用的免费 `mito0o852/OHLCV-1m` 数据集补齐。该数据标记为 `huggingface / finnhub-derived`，与 Alpaca 快照严格分开，未混合字段或分钟。

全过程仅调用历史市场数据接口。代码不导入 Alpaca trading client，不具备 broker、submit、cancel、账户、订单或持仓操作。Windows DPAPI 临时凭据缓存已在 Alpaca 下载成功后自动删除；凭据值没有写入仓库、日志或报告。

## 实际快照与覆盖率

### Alpaca IEX，split adjustment

| 环境 | 数据集 ID | 实际范围 | 行数 | XNYS 预期分钟 | 缺失 | 覆盖率 |
|---|---|---:|---:|---:|---:|---:|
| 2020 疫情期（Alpaca 可得部分） | `alpaca-iex-1min-61e39c3e6b4d876cc3336624573d9f12` | 2020-07-27—2020-12-31 | 426,133 | 1,572,960 | 1,146,827 | 27.091% |
| 2021 强趋势 | `alpaca-iex-1min-e44ab643818a7efc0da7a09f348d1fdc` | 2021-01-04—2021-12-31 | 1,047,725 | 1,569,600 | 521,875 | 66.751% |
| 2022 熊市 | `alpaca-iex-1min-55ea51fc2f7e7ff2e8065e4bf321b6d0` | 2022-01-03—2022-12-30 | 1,228,167 | 1,563,360 | 335,193 | 78.559% |
| 2023 混合环境 | `alpaca-iex-1min-b96642524b1a51aa2b9574335ca591b9` | 2023-01-03—2023-12-29 | 1,148,072 | 1,554,240 | 406,168 | 73.867% |
| 2024 混合环境 | `alpaca-iex-1min-dd31d6bae8aff19bf41d956330801680` | 2024-01-02—2024-12-31 | 1,115,623 | 1,563,840 | 448,217 | 71.339% |
| 2025 混合环境 | `alpaca-iex-1min-37291f29e2057075b207579edf6d244b` | 2025-01-02—2025-12-31 | 1,317,626 | 1,551,360 | 233,734 | 84.934% |
| 2026 Q1 | `alpaca-iex-1min-ccf623196d5fae6171b7ca5ef036d665` | 2026-01-02—2026-03-31 | 364,503 | 380,640 | 16,137 | 95.761% |
| 2026 盲测候选 | `alpaca-iex-1min-c399960d655fe2a36dfc2e51fbcc9259` | 2026-04-01—2026-08-12 | 534,544 | 574,080 | 39,536 | 93.113% |

所有上述当前格式快照均通过重复、非法 OHLCV、UTC/分钟节奏、XNYS 正常交易时段和复权价格异常门控；缺失分钟只记录，不补值。2025 快照从源响应中过滤了 94 行提前收盘后的记录。历史运行产生的旧格式同内容目录被保留，未覆盖或删除。

`late-2018-and-2019-transition` 的 Alpaca 请求返回零行，证据写入 `data/catalog/alpaca_iex_unavailable/`。单标的探针也确认 SPY 在 2020-01 和 2020-03 为零行，而 2021-01 有数据；这说明缺口来自本凭据可用历史范围，而非批量请求逻辑。

### 免费 HF/Finnhub-derived 缺口快照

| 环境 | 数据集 ID | 实际范围 | 行数 | XNYS 预期分钟 | 缺失 | 覆盖率 |
|---|---|---:|---:|---:|---:|---:|
| 2018 年末下跌及 2019 过渡 | `hf-finnhub-1min-aa583e6d9f6944f69ca163cd74de055a` | 2018-10-01—2019-12-31 | 1,912,026 | 1,951,200 | 39,174 | 97.992% |
| 2020 疫情暴跌与反弹 | `hf-finnhub-1min-3d3cb7a1f75c974e42905ebe78f91140` | 2020-01-02—2020-12-31 | 1,542,957 | 1,572,960 | 30,003 | 98.093% |

两个快照的发布数据均为 0 重复、0 非法 OHLCV、0 时段外分钟、0 节奏错误，价格异常门控通过。2020-12 源文件含 108 条重复记录，涉及 24 个“标的 + 交易日”组；为避免主观挑选记录，脚本隔离了整个受影响组并把清单写入质量证据。源复权状态只能声明为 `source-as-published; split-anomaly-gated`，不能等同于 Alpaca 的明确 split adjustment。

## 盲测边界

2026-04-01 后快照标记为 `blind_test_candidate=true`、`strategy_metrics_permitted=false`。本任务只读取并报告覆盖率和质量，没有运行、计算或查看任何策略收益。

## 复现命令

```powershell
$env:PYTHONPATH = "$PWD\src"

# Alpaca：审计、月度断点续传、校验和不可变发布
powershell -ExecutionPolicy Bypass -File scripts\run_alpaca_download.ps1

# 免费历史缺口：已验证月份会按哈希跳过
python scripts\acquire_hf_gap_1min.py --root G:\us-intraday-lab `
  --start-month 2018-10 --end-month 2020-12

# 发布并再次验证两个分源历史快照
python scripts\publish_hf_gap_snapshots.py --root G:\us-intraday-lab --repo .
```

Parquet、数据库、staging、日志和凭据均不进入 Git。月文件和快照存在时必须先通过哈希验证，脚本不会覆盖不同内容。

## 验证

- 快照发布函数在返回前重新计算内容哈希和数据集身份；
- 新增单元测试覆盖内容寻址发布及篡改拒绝；
- `python -m pytest -q`：838 passed；
- `python -m ruff check .`：通过；
- 两个新增/修改数据模块的严格 mypy：通过；
- 全仓 `python -m mypy src` 仍有 8 个既有错误，全部位于未修改的 `src/us_intraday_lab/long_horizon/orchestrator.py:676-681`。
