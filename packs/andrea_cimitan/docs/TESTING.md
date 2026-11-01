# Andrea Cimitan 包：安装和测试

本包是可运行的研究代理；先读 STRATEGY.md 和 RESEARCH.md 的资料边界。不是完整原版复现，不宣称盈利。想法 key：`andrea_cimitan`，目标登记簿的实际 id 尚未生成。

## 独立安装

在策略包仓库根目录、已安装真实 Freqtrade 2026.9 的环境运行：

```bash
python tools/packs.py install --pack andrea_cimitan --framework /path/to/freq-trader-framework
export FT_FRAMEWORK_ROOT=/path/to/freq-trader-framework
python -m pytest packs/andrea_cimitan/tests -q
```

安装器实际行为见根 README；勿覆盖自己的私有配置、生产代码或登记簿。需要离线安装时，将 user_data/strategies/AndreaCimitanORB.py 复制到框架同名目录，与 framework_base.py 并列。框架运行时由同目录导入基类；本包测试直接使用 FT_FRAMEWORK_ROOT 导入目标真实基类，根 conftest 仅辅助整库测试，不伪造 Freqtrade。

## 在目标框架的研究副本中选择

```bash
cd /path/to/freq-trader-framework
export FW_STRATEGY=AndreaCimitanORB
export FW_STRATEGY_PATH=user_data/strategies
export S03_FT_CONFIG=user_data/config-test-okx.json
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
s03ft doctor --research --json
```

环境选择不会改原 config 的 strategy、dry_run、pair_whitelist 或风险参数。不运行 freqtrade trade，不调用真实下单接口。插件只给 BTC/USDT:USDT、ETH/USDT:USDT 发信号；配置的其他币仍可能需要日线数据用于父类订阅。

## 在看收益前登记

先读策略证伪条件，并根据数据可用性确定拟测试完整区间及最后约三成样本外段，再登记。日期一旦登记不得在看到收益后移动。下面 id 和日期是必须填写的占位符，不能直接当成真实记录：

```bash
s03ft lab idea add --title 'AndreaCimitanORB v1' \
  --hypothesis 'Closed-bar price proxy may have positive net expectancy' \
  --mechanism 'Defined setup and causal timing in package STRATEGY.md' \
  --falsification 'Nonpositive holdout expectancy or failed cost and delay stress' \
  --source agent --ref 'andrea_cimitan/STRATEGY.md'
IDEA='填入实际返回的编号'
s03ft lab idea holdout --id "$IDEA" --start 'YYYY-MM-DD'
s03ft lab idea move --id "$IDEA" --to screening --reason 'specification frozen before outcomes'
s03ft lab idea move --id "$IDEA" --to backtesting --reason 'first frozen candidate including G0 baseline'
```

不要复制别人的 ideas.jsonl 来覆盖既有记录。G0 内部也运行回测，所以尝试登记要在 G0 前完成。代码参数改变、过滤器改变及细周期对照都需按框架记录新尝试。

## 数据、偏差和组合测试

```bash
freqtrade download-data -c "$S03_FT_CONFIG" --timeframes 5m 1d 1m \
  --timerange '填入预定区间并包含前置历史' --trading-mode futures
s03ft research g0 --timerange '预先确定的开发段'
s03ft events build --out research/events_history.json --history
s03ft research portfolio --all --idea "$IDEA" --trials base,stop_floor \
  --timerange '预先确定的完整区间'
s03ft research verdict --idea "$IDEA"
```

命令中的日期占位符需先替换，不能把错误格式当作跑完验证。下载原白名单所有币的日线并审核时间缺口；确认 futures、mark 和 funding_rate 的真实覆盖，不能将缺失资金费率补零后称为完整多年净收益。1m 是执行诊断数据，组合包装器默认不自动采用。

完整 G0 未运行；必须看真实偏差分析结果和信号数，而不是只看退出码。base 和 stop_floor 若没有实际不同结果，不足以满足 PBO 候选要求。cost2x、delay1、stopslip 全部保留。低周期止损若被原0.8%下限大量拒绝，应报告拒绝率，不改下限凑数。

使用直接 freqtrade backtesting 做1m对照时，仅对该研究进程设置 S03_EVENTS_REQUIRED=0、S03_EVENTS_FILE=research/events_history.json、S03_NEWS_FILE='' 和独立 S03_RISK_LOG；同时用 --enable-protections --cache none --export trades --backtest-directory 指向独立目录。不可全局关闭生产守卫，不把细周期诊断替换组合主证据。

## 如何判读

核对止损绝对价与实际绑定 stop_px、订单计划、净R、费用占风险比例、漏单和时间退出。采样式目标不是静态TP限价单，盘中碰到目标不保证回测／实盘都成交。不得用单元测试数量或交易员业绩宣传替代收益证据。

G0–G9依框架逐步完成，G7还要验证滚动窗口、重启和相同输入逐条信号一致性。模拟和小额实盘须按框架流程及人类授权进行，本包没有执行或批准这些阶段。
