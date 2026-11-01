# v2 测试与安装（2026-11-01）

必须使用新版双向框架（manifest.json 的 commit 与基类校验和），Freqtrade 2026.10、Python >=3.12。旧3fe6153框架不能执行此版。先安装/检出框架升级，再复制插件；安装器不替换框架基类、不启用交易。空头与新增币种尚未市场验证。配置细节见仓库 docs/CONFIGURATION.md，独立ZIP使用 STRATEGY.md 顶部 v2 规则。

# ImreGamsAuctionProxy 安装与测试

先读 [规格与裁剪范围](STRATEGY.md)。本包只能检验 OHLCV 平衡／回归代理；没有 L2、真实订单方向、期权链或组合风险引擎。

在策略包仓库：

```bash
python tools/packs.py install --pack imre_gams --framework <framework>
export FT_FRAMEWORK_ROOT=<framework>
python -m pytest packs/imre_gams/tests -q
```

或者只复制 `user_data/strategies/ImreGamsAuctionProxy.py` 到现有 FrameworkStrategy 所在目录。不要覆盖配置、风险基类或登记簿。使用 Freqtrade 2026.10，目标是研究副本。

进入目标框架之后：

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export FW_STRATEGY=ImreGamsAuctionProxy
export FW_STRATEGY_PATH=user_data/strategies
export S03_FT_CONFIG=user_data/config-test-okx.json
s03ft doctor --research --json
s03ft lab idea add --title 'Imre balanced-range OHLCV proxy v1' \
 --hypothesis 'Low-efficiency balanced ranges may favour failed downside break reversion' \
 --mechanism 'Price re-enters an established range after a downside excursion' \
 --falsification 'Regime filtering fails to improve net return or directional repricing dominates' \
 --source agent --ref 'packs/imre_gams/docs/STRATEGY.md'
```

保留实际返回的 id，在第一次市场回测前登记样本外、screening 和 backtesting。低效率指标是自定义走势几何，不代表已经证实真实拍卖环境或对手方被迫平仓。

```bash
freqtrade download-data -c "$S03_FT_CONFIG" --timeframes 1h 1d 5m \
 --timerange <包含预热的区间> --trading-mode futures
s03ft research g0 --timerange <开发段>
s03ft events build --out research/events_history.json --history
s03ft research portfolio --all --idea <实际id> --trials base,stop_floor --timerange <预登记区间>
s03ft research verdict --idea <实际id>
```

占位参数不应原样运行。保留全部 cost2x、delay1、stopslip；区分宽度、效率、成交量三种筛选的边际作用。样本外日期不能在看见收益后修改。原白名单仍需要日线相关性数据，不仅下载两个信号品种。

检查 enter_tag 中当时 midpoint 是否跟订单保存，后续范围变化不得重算旧目标。真实成交偏离信号价后，毛 1.5 倍空间检查不等于真实净风险收益比；应统计漏单、时间退出与尾部止损。

直接 `freqtrade backtesting` 细周期对照时，只对该研究进程显式指定历史事件环境（`S03_EVENTS_REQUIRED=0`、`S03_EVENTS_FILE`）、清空研究新闻守卫、设置独立 `S03_RISK_LOG` 和结果路径，并保留 `--export trades --cache none --enable-protections`。不全局关闭生产守卫。资金费、标记价和滑点不完整时，不能把名义方向中性或近均值回归当作安全证明。

这份策略不支持用期权获利缓冲期货亏损，也不执行不设止损、裸卖期权或识别实际机构仓位。G0–G9 仍由完整市场研究验证，本包不包含真实交易命令。
