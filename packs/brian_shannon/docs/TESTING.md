# BrianShannonAVWAP 安装与测试

先阅读 [研究规格](STRATEGY.md) 与 [原研究](RESEARCH.md)。本包只提供一个常规确认入场的 OHLCV 代理，不含接急跌例外及原版移动止损。

## 安装

在策略包仓库运行以下命令，把 `<framework>` 换成独立研究框架副本：

```bash
python tools/packs.py install --pack brian_shannon --framework <framework>
```

安装器不应覆盖框架配置和想法登记簿。也可只把 `user_data/strategies/BrianShannonAVWAP.py` 复制到目标框架同名目录，保留原 framework_base.py。框架固定版本为 Freqtrade 2026.9。

在策略包仓库运行专用测试，使用已装真实框架依赖的解释器：

```bash
export FT_FRAMEWORK_ROOT=<framework>
python -m pytest packs/brian_shannon/tests -q
```

## 在目标框架开展市场研究

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export S03_FT_CONFIG=user_data/config-test-okx.json
export FW_STRATEGY=BrianShannonAVWAP
export FW_STRATEGY_PATH=user_data/strategies
s03ft doctor --research --json
s03ft lab idea add --title 'Shannon AVWAP confirmation proxy v1' \
 --hypothesis 'Causal anchor reclaim may improve net trend pullback entries' \
 --mechanism 'Observed recovery above volume-weighted reference within daily uptrend' \
 --falsification 'No out-of-sample improvement over the same setup without AVWAP' \
 --source agent --ref 'packs/brian_shannon/docs/STRATEGY.md'
```

记录返回的真实 id；回测前使用它登记样本外起点，并先推进 screening／backtesting。不要复制其他项目登记号。日线方向需要足够预热和 1h 数据，父类相关性还需要原白名单全部品种日线。公开下载用已有配置，不修改白名单和风险：

```bash
freqtrade download-data -c "$S03_FT_CONFIG" --timeframes 1h 1d 5m \
 --timerange <包含预热的起止区间> --trading-mode futures
s03ft research g0 --timerange <开发段>
s03ft events build --out research/events_history.json --history
s03ft research portfolio --all --idea <实际id> --trials base,stop_floor --timerange <预登记区间>
s03ft research verdict --idea <实际id>
```

以上含 `<…>` 的位置必须替换，不能当作直接可运行的日期或 id。比较参数前先登记每次尝试；不要根据结果移动样本外起点。所有三项压力方案保留；因子筛选只作辅助，不代替 AVWAP 策略验证。

## 数据与执行重点

核对成交量单位、单一交易所代表性、低点确认延迟、切日、锚点重置及有限窗口重启。实际部署应对完整历史与滚动历史逐条比对信号。日线不可提前合并；不能以事后低点画锚点。分批可能因最小下单额未成交，需读取实际订单和风险记录。

若另做直接 `freqtrade backtesting` 细周期诊断，应只对该研究进程设置 `S03_EVENTS_REQUIRED=0`、历史 `S03_EVENTS_FILE`、空 `S03_NEWS_FILE` 及独立 `S03_RISK_LOG`，并使用独立输出目录、`--export trades --cache none --enable-protections`。不能在生产环境全局关闭守卫；不能把不完整资金费数据补零后宣称多年净收益可信。

G0、组合统计、样本外、G7 重启一致性与四周模拟尚需目标环境执行。无真实订单命令，不批准上线。
