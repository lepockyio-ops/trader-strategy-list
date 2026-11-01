# Trader Strategy Packs

为 [freq-trader-framework](https://github.com/lepockyio-ops/freq-trader-framework) 编写的 **11 位交易员研究策略包**。每位独立一包，包含研究报告、明确规格、可运行插件、测试与验证记录。所有实现均为研究代理，不能称为交易员授权原版，也不代表经过收益验证。

框架兼容基线：`3fe6153ccec5eb0598ce3dbf2e38ea0bc79ce90c`；Freqtrade `2026.9`。只生成 BTC/USDT:USDT、ETH/USDT:USDT 多头候选。包不包含框架风控代码或交易配置，须安装到单独的目标框架研究副本。

## 策略索引

| 交易员 | 包目录 | 可检验的方向 | 主要适配边界 |
|---|---|---|---|
| Trader Mayne | [trader_mayne](packs/trader_mayne/docs/STRATEGY.md) | 高周期结构与周初更高低点代理 | 具体摆动点和恢复触发为补充定义 |
| Martin Luk | [martin_luk](packs/martin_luk/docs/STRATEGY.md) | 强趋势中回调后的动量恢复 | 股票选股与超低周期精确执行未复刻 |
| Mark Minervini | [mark_minervini](packs/mark_minervini/docs/STRATEGY.md) | 趋势模板、波动收缩与突破 | 股票基本面及原版主观 VCP 另有条件 |
| Vibha Jha | [vibha_jha](packs/vibha_jha/docs/STRATEGY.md) | 趋势持有与分阶段管理 | 成长股研究、TQQQ 产品逻辑不能直接移植 |
| Pradeep Bonde | [pradeep_bonde](packs/pradeep_bonde/docs/STRATEGY.md) | 动量爆发与快速兑现 | 没有原生催化剂／主题辨识，价格量代理 |
| Brian Shannon | [brian_shannon](packs/brian_shannon/docs/STRATEGY.md) | 多周期趋势与因果锚定 VWAP | OHLCV 量加权均价不是逐笔 AVWAP |
| Peter Brandt | [peter_brandt](packs/peter_brandt/docs/STRATEGY.md) | 经典整理形态突破 | 选择一种明确图形代理，不包含全部形态体系 |
| Carmine Rosato | [carmine_rosato](packs/carmine_rosato/docs/STRATEGY.md) | 关键位置拒绝与重新站回 | OHLCV 不能证明被动吸收或真实订单流 |
| Chris Creamer | [chris_creamer](packs/chris_creamer/docs/STRATEGY.md) | 失败拍卖与回归的价格代理 | 没有 DOM、footprint、逐笔主动成交证据 |
| Imre Gams | [imre_gams](packs/imre_gams/docs/STRATEGY.md) | 环境过滤后的价值回归代理 | 未实现真实参与者约束、Gamma、期权组合 |
| Andrea Cimitan | [andrea_cimitan](packs/andrea_cimitan/docs/STRATEGY.md) | 开盘区间突破与成交量过滤 | 未实现 MBO 大单识别、期权卖方组合 |

每包 `docs/RESEARCH.md` 保留此前研究的证据与适用边界；`STRATEGY.md` 是本次明确化定义；`VALIDATION.md` 只记录实际完成的验证。股票、订单流和期权的方法迁移时，缺失环节不会被 OHLCV 图形自动补齐。

## 快速开始

先准备目标框架（Linux/macOS 为其受支持环境），按该框架说明安装其依赖。本库可使用同一虚拟环境：

```bash
git clone https://github.com/lepockyio-ops/freq-trader-framework.git ../freq-trader-framework
git -C ../freq-trader-framework checkout 3fe6153ccec5eb0598ce3dbf2e38ea0bc79ce90c
export FT_FRAMEWORK_ROOT="$(cd ../freq-trader-framework && pwd)"
# 在框架虚拟环境中，或用该虚拟环境的 Python 执行以下命令。
python tools/packs.py list
python tools/packs.py install --pack martin_luk --framework "$FT_FRAMEWORK_ROOT"
pytest packs/martin_luk/tests -q
```

安装器只复制策略、测试、文档，检查框架基类 SHA256（CRLF 统一为 LF，兼容 Windows／Linux），并拒绝覆盖不同内容。它不复制行情、密钥、配置或想法登记簿，不改变默认 MyStrategy，也不自动启动任何交易。

安装后在**框架研究目录**选择研究策略，类名见 `manifest.json`：

```bash
export FW_STRATEGY=MartinLukPullback
export FW_STRATEGY_PATH=user_data/strategies
export S03_FT_CONFIG=user_data/config-test-okx.json
s03ft doctor --research --json
```

这只影响该研究命令的策略选择，不是上线批准。完整流程见 [统一研究流程](docs/RESEARCH_WORKFLOW.md)，各包另有周期、数据、入场及退出说明。

## 下载单包和验证

`dist/` 提供每位的 ZIP、各自 SHA256 和归档清单。也可从源码重建：

```bash
python tools/packs.py build --pack all
export FT_FRAMEWORK_ROOT=/absolute/path/to/freq-trader-framework
pytest -q
```

根目录测试需要目标框架真实 `framework_base.py`，不会用假类替代。跨包测试结果见 [验证总览](docs/VALIDATION_SUMMARY.md)。单元测试及因果检查不能替代真实成交、成本后收益、G0–G9 和人工审阅。

本次不复制原框架源码、不改变其风险约束，不运行实盘命令。每个插件的数值起点均为示例，尚未经过市场统计验证；不能根据交易员声望推断该代理有正期望。

