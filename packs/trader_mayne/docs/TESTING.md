# v2 测试与安装（2026-11-01）

必须使用新版双向框架（manifest.json 的 commit 与基类校验和），Freqtrade 2026.10、Python >=3.12。旧3fe6153框架不能执行此版。先安装/检出框架升级，再复制插件；安装器不替换框架基类、不启用交易。空头与新增币种尚未市场验证。配置细节见仓库 docs/CONFIGURATION.md，独立ZIP使用 STRATEGY.md 顶部 v2 规则。

# Trader Mayne 插件：安装与测试

这是研究插件，不是已验证策略。先读 [完整规格](STRATEGY.md) 与仓库 AGENTS.md。基线为 `3fe6153ccec5eb0598ce3dbf2e38ea0bc79ce90c`；交付不修改任何交易配置或框架风控。不运行实盘命令。

## 1. 在你的研究副本安装

把交付中的策略放入 `user_data/strategies/`，测试放入 `tests/`，文档放入 `docs/`。若使用补丁，先在研究副本运行 `git apply --check <补丁路径>`，确认没有冲突再应用。不要覆盖你已有的想法登记簿、私有配置或行情。

框架官方面向 Linux/macOS；Windows 本次能够运行新插件测试，但不代表部署脚本兼容 Windows。建议使用你原有的受支持研究环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[trade,test]'
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export S03_FT_CONFIG=user_data/config-test-okx.json
export FW_STRATEGY=TraderMayneWeeklyHL
export FW_STRATEGY_PATH=user_data/strategies
pytest tests/test_trader_mayne.py -q
s03ft doctor --research --json
```

上述环境变量只选择研究命令的策略，不把配置中的 `MyStrategy` 替换成新策略，不改变 dry_run、pair_whitelist、max_open_trades。实际操作前确认没有连接到生产服务的运行目录。

Windows 当前副本可用：

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:S03_FT_CONFIG='user_data/config-test-okx.json'
$env:FW_STRATEGY='TraderMayneWeeklyHL'
$env:FW_STRATEGY_PATH='user_data/strategies'
$env:PATH="$PWD/.venv/Scripts;$env:PATH"
& '.venv/Scripts/python.exe' -m pytest tests/test_trader_mayne.py -q
& '.venv/Scripts/python.exe' -m s03ft.cli doctor --research --json
```

Windows 全仓测试使用独立临时目录，例如 `--basetemp var/pytest-local`，不要把该目录指定成任何已有数据目录。UTF-8 对 Python 子进程也要生效，不能只设置终端显示编码。

## 2. 先登记，再看收益

当前交付副本登记号为 `I-20261030-001`，样本外 2025-05-01 在任何市场回测前登记。这个号只属于当前登记簿。新研究副本请生成自己的号，并在后续命令中替换，不复制覆盖已有登记簿。

```bash
s03ft lab idea add --title 'Mayne weekly HL v1' \
  --hypothesis 'Confirmed daily HH-HL plus early-week recovery may have positive net expectancy' \
  --mechanism 'Higher-timeframe continuation after a weekly pullback' \
  --falsification 'Nonpositive holdout expectancy, failed stress, or no robust weekday advantage' \
  --source agent --ref 'STRATEGY.md'
# 将上一步实际返回的 id 填入 IDEA，不能把示例号当作已经存在。
IDEA='填入实际登记号'
s03ft lab idea holdout --id "$IDEA" --start 2025-05-01
```

计划区间为 20220101–20261001，结束边界不含；拟样本外为 2025-05-01 起。若你的可用数据不能覆盖这个区间，必须在看收益前另建研究设计和登记号，不能根据已见结果移动样本外起点。

## 3. 准备数据并审计覆盖

```bash
freqtrade download-data -c "$S03_FT_CONFIG" --timeframes 1h 1d 5m \
  --timerange 20210101-20261001 --trading-mode futures
```

不传 `--pairs` 时保留框架已有白名单，以便五币日线相关性订阅有数据。插件仍只为 BTC/USDT:USDT 与 ETH/USDT:USDT 产生信号。下载 5m 用于后续细周期执行对照，框架组合主回测默认不会自动采用它。

必须检查：每个品种首末时间、内部缺口、UTC 切日、mark 数据、funding_rate 数据。当前 OKX API 对多年价格数据和资金费率历史的覆盖不同；只下载到近三个月资金费率不等于多年净成本齐全。不要为了跑通将缺失资金费率任意设为 0，或把不连续历史拼成完整证据。

五币横截面因子筛选不直接检验“何时入场”。若辅助筛因子，可执行：

```bash
s03ft lab factors --coins BTC,ETH --mode time_series --tf 1d --horizon 3
```

这只是仓库内置因子的诊断，不是本插件机制已通过筛选，更不能将某个内置因子的显著性嫁接给本策略。

## 4. G0 与组合主证据

```bash
# 登记每次策略／参数尝试；G0 内部也运行回测，所以登记必须在 G0 之前。
s03ft lab idea move --id "$IDEA" --to screening --reason 'spec frozen; data audited'
s03ft lab idea move --id "$IDEA" --to backtesting --reason 'v1 first test; no outcome-based tuning'
s03ft research g0 --timerange 20220101-20250101
s03ft events build --out research/events_history.json --history
s03ft research portfolio --all --idea "$IDEA" --trials base,stop_floor \
  --timerange 20220101-20261001
s03ft research verdict --idea "$IDEA"
```

登记 backtesting 应在首次收益回测前执行；当前副本已完成这一步，不重复当成新发现。G0 使用开发段，不应利用样本外来修补信号。G0 返回命令成功还不够，需要检查偏差结果、信号数量与每个分析子命令是否实际完成；零信号不等于得到有力的无前视证明。

base 与 stop_floor 是框架支持的不同候选；若实际结果相同，PBO 的候选要求仍可能不满足。`--all` 保留 cost2x、delay1 和 stopslip；不得删除压力方案以通过门槛。

**细周期执行诊断**：

```bash
s03ft lab idea move --id "$IDEA" --to backtesting --reason 'separate 5m execution diagnostic'
mkdir -p research/results
RUN_DIR="$(mktemp -d research/results/mayne-detail-XXXXXX)"
S03_EVENTS_REQUIRED=0 S03_EVENTS_FILE=research/events_history.json \
  S03_NEWS_FILE='' S03_RISK_LOG="$RUN_DIR/risk.jsonl" \
  freqtrade backtesting -c "$S03_FT_CONFIG" --strategy TraderMayneWeeklyHL \
  --strategy-path user_data/strategies --timerange 20220101-20250101 \
  --timeframe-detail 5m --enable-protections --cache none \
  --export trades --backtest-directory "$RUN_DIR"
```

这是独立诊断，运行前登记新的尝试并给它独立输出路径；命令只对该研究进程使用历史事件文件，不把生产守卫全局关闭。不能把这个独立结果冒充组合清单中的 base，也不能遗漏风险日志后拿不完整 R 做上线判断。不要因为 5m 结果更好便事后更换主证据口径。

## 5. 应怎样读结果

先看交易数与拒绝原因：日线结构不足、非周初、没有回调、首候选用完、止损距离、事件、相关性、资金预算和漏单。低频候选很少时，统计结论可能长期为证据不足，这是策略特征，不应靠放宽护栏解决。

再看净期望及区间、最大回撤、周收益分布、最长连亏、样本外、币种／年份贡献集中度和压力表现。检查框架输出 `data_gaps`、初始风险记录和退出原因。毛价格 2R 不能替代净 R。零交易方案和失败任务不能从结果中删除。

G7 要比较完整历史、有限滚动窗口和重启后的逐条信号。日线最近两个 pivot 使用历史保留；很长的单边行情可能使旧 pivot 超出实时窗口，导致缺少方向许可。本次前缀测试证明无未来依赖，不证明所有有限窗口都能重现。

G8 四周且至少二十笔模拟，以及 G9 书面授权的小额实盘都未由此交付完成。仓库限制 agent 不运行 `freqtrade trade`，本文也不提供自动上线命令。

## 6. 本次验证状态

实际运行结果、失败原因和独立审查见 [验证记录](VALIDATION.md)。配置不变、专用单元测试通过，不等于市场优势被验证。结论以证据为准，不能把源交易者知名度当作回测。
