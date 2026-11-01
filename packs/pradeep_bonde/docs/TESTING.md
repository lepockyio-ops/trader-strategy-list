# v2 测试与安装（2026-11-01）

必须使用新版双向框架（manifest.json 的 commit 与基类校验和），Freqtrade 2026.10、Python >=3.12。旧3fe6153框架不能执行此版。先安装/检出框架升级，再复制插件；安装器不替换框架基类、不启用交易。空头与新增币种尚未市场验证。配置细节见仓库 docs/CONFIGURATION.md，独立ZIP使用 STRATEGY.md 顶部 v2 规则。

# PradeepBondeBurst：接入与测试步骤

先读STRATEGY.md与RESEARCH.md；本插件是研究代理。实际idea id必须在目标登记簿生成；没有已注册的默认id，不覆盖research/ideas.jsonl。原框架支持Linux/macOS；本次只用实际Freqtrade2026.10作逻辑测试。

## 1. 安装与专用测试

在本仓库设置FT_FRAMEWORK_ROOT指向已安装的freq-trader-framework研究副本，然后：

```bash
python tools/packs.py install --pack pradeep_bonde --framework /path/to/freq-trader-framework
FT_FRAMEWORK_ROOT=/path/to/freq-trader-framework python -m pytest packs/pradeep_bonde/tests -q
```

安装器仅复制策略、测试和文档，不改交易配置。切换至框架研究副本后使用环境选择：

```bash
export FW_STRATEGY=PradeepBondeBurst
export FW_STRATEGY_PATH=user_data/strategies
export S03_FT_CONFIG=user_data/config-test-okx.json
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
s03ft doctor --research --json
```

## 2. 登记与冻结设计

```bash
s03ft lab idea add --title 'pradeep_bonde research v1' --hypothesis 'The specified causal proxy may have positive net expectancy' --mechanism 'See the frozen strategy specification' --falsification 'Nonpositive holdout or failed stress tests' --source agent --ref 'docs/pradeep_bonde/STRATEGY.md'
```

将实际返回id放入IDEA；先选择数据区间与样本外，不因收益改变。示例设计（不是已验证）：20220101–20261001，holdout起点2025-05-01。新数据覆盖不足时，在看收益前重新设计并登记，不移动已看过结果的样本外。

```bash
IDEA='填入实际返回id'
s03ft lab idea holdout --id "$IDEA" --start 2025-05-01
s03ft lab idea move --id "$IDEA" --to screening --reason 'spec frozen and data audited'
s03ft lab idea move --id "$IDEA" --to backtesting --reason 'first attempt before G0 and returns'
```

## 3. 数据与正式验证

```bash
freqtrade download-data -c "$S03_FT_CONFIG" --timeframes 1h 1d 5m --timerange 20210101-20261001 --trading-mode futures
s03ft events build --out research/events_history.json --history
s03ft research g0 --timerange 20220101-20250101
s03ft research portfolio --all --idea "$IDEA" --trials base,stop_floor --timerange 20220101-20261001
s03ft research verdict --idea "$IDEA"
```

保留框架已有白名单，不设置更宽风险。审计所有白名单日线、内部缺口、UTC、mark和funding实际覆盖；OKX多年价格并不代表多年资金费齐全。主证据采用组合回测，cost2x/delay1/stopslip全部保留；单币×年份诊断不能替代组合。两个候选实际相同时不能假称PBO充分。

## 4. 执行与解释

本策略信号周期1h；限价、费用、滑点、最小数量、资金费和父类更优成交止损政策都影响净结果。回调退出和分批不保证每个盘中目标触价成交。直接freqtrade细周期诊断若绕过research包装器，应仅该研究进程使用S03_EVENTS_REQUIRED=0、S03_EVENTS_FILE=历史事件、S03_NEWS_FILE=''和独立S03_RISK_LOG、输出目录；不得全局关闭生产守卫。

单元测试不是G0或正期望证据；独立样本外、全滚动重启G7、四周模拟G8及书面授权G9另行完成。不运行freqtrade trade，不自动批准或上线。
