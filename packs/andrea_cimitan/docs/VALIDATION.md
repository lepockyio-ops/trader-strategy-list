# Andrea Cimitan v1 验证记录

日期：2026-11-01。目标基线：freq-trader-framework `3fe6153ccec5eb0598ce3dbf2e38ea0bc79ce90c`，真实 Freqtrade 2026.9；Windows Python 3.12。策略类 `AndreaCimitanORB`，周期 5m。

## 已核验事实

本次实现前先写 STRATEGY.md。实际运行三包联合测试：

```text
python -m pytest packs/carmine_rosato/tests packs/chris_creamer/tests packs/andrea_cimitan/tests -q
34 passed
```

本包收集 12 项测试，覆盖实际正信号、缺失条件拒绝、前缀／未来扰动、绝对止损／退出和受保护父类回调继承。此处数字来自真实命令输出，不是市场交易笔数。目标基类未被替换为假实现。后续集成验证结果若由根报告追加，以实际输出为准。

## 证据与限制

- 来源方观点：先前研究报告 RESEARCH.md，里面已标原材料边界；Carmine、Andrea依据所附字幕，Chris依据此前公开材料整理，不补造原字幕。
- 模型推断：本插件的具体阈值、OHLCV过滤与退出规则，全部是未验证的研究设计。没有真实L2、足迹、MBO、主动买卖或机构身份数据。
- 未知／未完成：未运行本包市场回测、官方G0、样本外、cost2x／delay1／stopslip市场压力、组合收益检验、G7–G9。不声称存在正期望或可以上线。
- 框架边界：framework_params为空，未覆盖定仓、杠杆、成交、止损和风险退出等受保护回调；没有改配置／白名单／dry_run，没有真实交易。

## 后续验证要求

根据 TESTING.md 在自己的登记簿生成真实 id、冻结数据与样本外起点，保持框架门槛。总成交量不能证明吸收或大买方，代理结果不能直接证明原交易员方法成败。成本、资金费历史、滑点、漏单与细周期采样差异必须进入结论。
