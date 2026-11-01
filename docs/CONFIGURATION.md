# 币种、多空方向与 v2 升级

v2 要求 Python >=3.12、Freqtrade ==2026.10，以及 manifest.json 指定的新框架提交。旧 `3fe6153…` 只是 v1 当时测试的源代码快照，不是 Freqtrade 版本；它的止损与风险回调不能正确管理本版空单。不要只复制插件到旧基类，也不要删除安装器的兼容检查。

## 一处设置交易币种

`exchange.pair_whitelist` 使用精确合约名称，是策略交易范围的唯一币种列表。默认五币：

```json
{
  "exchange": {
    "pair_whitelist": [
      "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
      "BNB/USDT:USDT", "HYPE/USDT:USDT"
    ],
    "pair_blacklist": []
  },
  "fw_trade_direction": "both"
}
```

删除某项即可关闭该币；追加如 `ADA/USDT:USDT` 可纳入该币；`[]` 禁止全部新入场。策略默认五币仅用于未提供名单的研究实例；正常运行应始终显式填写名单。黑名单继续生效。使用 StaticPairList，列表填写完整名称，不使用正则或动态 PairList 绕过范围。

这不会保证任一交易所提供这些市场，也不会证明策略在新增币种有效。先核验交易所的 USDT 线性永续合约、历史数据、最小名义金额、精度和维持保证金档位。新增币种沿用框架保守的 `_default` 保证金估算，未按真实档位完成实盘核验。

## 选择方向

| direction | 新入场 |
|---|---|
| `both`（默认，用户要求） | 允许多或空候选 |
| `long` | 只允许多单 |
| `short` | 只允许空单 |

错误拼写会报错／拒绝入场，不退回默认放行。方向开关作用于新开仓；已有交易仍正常执行止损、分批和退出。配置变更需重新加载，不是立即撤单或平仓命令。Freqtrade 采用单向持仓模式：同一合约不同时持有多空，`both` 不是 hedge mode。双向策略要求 `trading_mode=futures`、`margin_mode=isolated`，不能把本版 `can_short=True` 的类用于现货。

## 在研究副本测试

示例覆写文件是 [configs/trading-policy.example.json](../configs/trading-policy.example.json)。复制后按需要编辑，通过 Freqtrade 的多个 `-c` 合并加载；它只包含币种和方向，不替代基础交易配置。

```bash
freqtrade backtesting -c user_data/config-test-okx.json \
  -c /absolute/path/to/trading-policy.example.json \
  --strategy MartinLukPullback --strategy-path user_data/strategies \
  --timerange '事先冻结的研究区间' --enable-protections --cache none
```

这是研究命令形状，区间须替换，并先按 [研究流程](RESEARCH_WORKFLOW.md) 登记想法、样本外与尝试。若使用研究包装器，其配置读取方式以框架说明为准；可在独立研究基础配置中填入相同字段，不把临时覆写遗漏在正式研究证据之外。

所有启用币种都要下载策略要求周期、1d 相关性数据、mark 和 funding_rate。独立监控的 `monitor/monitor.toml` 中 `pairs` 也需同步；因子研究的 `--coins` 同步调整。新增币种不自动获得原新闻词典的识别覆盖。

## 策略空头的含义

11 包均有明确空头条件和反向离场，详见各 `STRATEGY.md` 顶部 v2 章节。空头是本次模型推断的研究扩展，尤其不能称为 Minervini、Vibha、Bonde 股票多头方法的原版空头系统。止损距离、单笔风险、总风险、事件守卫和压力情景保留；空头资金费按保守成本预留，不能假定必有资金费收入。

使用全新研究副本安装 v2。安装器拒绝覆盖不同内容；已有 v1 文件应先由用户备份并审阅迁移，不以强制覆盖方式吞掉个人改动。v1 的市场或工程验证不能作为 v2 新币种、新方向的盈利证据。

本版方向字段与框架最新主分支一致：`fw_trade_direction`；单币可覆盖，如 `"fw_pair_directions": {"HYPE/USDT:USDT": "long"}`。未写覆盖的币沿用全局方向。原讨论中的 trading_policy.direction 未作为发布接口；请使用此处 fw_ 字段。
