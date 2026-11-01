# v2 测试与安装（2026-11-01）

必须使用新版双向框架（manifest.json 的 commit 与基类校验和），Freqtrade 2026.10、Python >=3.12。旧3fe6153框架不能执行此版。先安装/检出框架升级，再复制插件；安装器不替换框架基类、不启用交易。空头与新增币种尚未市场验证。配置细节见仓库 docs/CONFIGURATION.md，独立ZIP使用 STRATEGY.md 顶部 v2 规则。

# PeterBrandtRectangle 安装与测试

先读 [研究规格](STRATEGY.md)。本版是日线水平矩形代理，不是所有经典图形；不缩短六周形成期去提高频率。

在策略包仓库：

```bash
python tools/packs.py install --pack peter_brandt --framework <framework>
export FT_FRAMEWORK_ROOT=<framework>
python -m pytest packs/peter_brandt/tests -q
```

也可手动复制 `user_data/strategies/PeterBrandtRectangle.py`，不要覆盖 framework_base.py 或交易配置。目标为独立研究副本和 Freqtrade 2026.10。

目标框架中的研究选择：

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export FW_STRATEGY=PeterBrandtRectangle
export FW_STRATEGY_PATH=user_data/strategies
export S03_FT_CONFIG=user_data/config-test-okx.json
s03ft doctor --research --json
s03ft lab idea add --title 'Brandt rectangle proxy v1' \
 --hypothesis 'A predefined daily rectangle with explicit failure exits may have positive net expectancy' \
 --mechanism 'Horizontal balance ends with a confirmed upside breakout' \
 --falsification 'Failed breakouts or time exits erase net gains in unseen data' \
 --source agent --ref 'packs/peter_brandt/docs/STRATEGY.md'
```

用命令返回的实际 id 登记样本外和尝试状态，必须早于收益回测及 G0。冻结时间区间，不按图形结果重选样本。没有注册号时不编造一个数字。

```bash
freqtrade download-data -c "$S03_FT_CONFIG" --timeframes 1d 1h \
 --timerange <包含日线预热的区间> --trading-mode futures
s03ft research g0 --timerange <开发段>
s03ft events build --out research/events_history.json --history
s03ft research portfolio --all --idea <实际id> --trials base,stop_floor --timerange <预登记区间>
s03ft research verdict --idea <实际id>
```

上述占位日期／id 必须自行替换。1h 数据用于后续执行诊断；组合主回测是否用 detail 需要独立声明，不能暗换口径。已有白名单各币的日线仍供相关性；插件只对 BTC、ETH USDT 永续发信号。

重点记录所有矩形候选及 stop_min／stop_max 拒绝。形态跨度六周而止损在整形态底部，可能大多超出原框架 3% 示例护栏；不要因此改护栏、缩短形态或偷换到无关的小低点。比较时间退出时要明确日线 UTC 开始／结束、真实入场时刻及成本口径。

直接细周期诊断需先登记尝试，只对研究进程设置 `S03_EVENTS_REQUIRED=0`、历史事件文件、空新闻守卫变量、独立风险日志和输出目录，使用真实费率及 `--cache none --enable-protections --export trades`。未补齐资金费不得补零充当多年净收益；静态价格目标与回调采样退出分开理解。

G0–G9 不降低，尤其低频策略不保证短期达到统计笔数。没有真实交易或自动上线步骤。实际状态见 VALIDATION.md。
