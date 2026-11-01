# 从研究包到框架验证

## 先明确“完整包”的范围

完整指可独立阅读、安装、计算候选信号和测试的工程包，包含原研究、转换规则、止损／退出、测试与数据缺口。它不表示完整复制交易员所有主观、股票基本面、订单流、期权或组合业务。特别是 OHLCV 无法唯一推断主动成交、吸收、冰山订单、机构身份、dealer Gamma 或实际止损。

本库统一沿用原框架的风险管理；v2 使用明确升级后的双向框架，不支持期权交易系统。未实现环节在每包资料中保留，不给出虚构收益。

## 研究登记先于收益测试

每包的 slug 是本库研究键，不是已经登记的目标框架想法号。安装器不写入登记簿。使用者在目标研究副本执行：

```bash
s03ft lab idea add --title '所选包名称与版本' \
  --hypothesis '从 STRATEGY.md 复制本次待检验假设' \
  --mechanism '从 STRATEGY.md 复制经济或行为机制' \
  --falsification '写明哪些样本外和成本结果会推翻假设' \
  --source agent --ref '该包 STRATEGY.md 与本库提交版本'
```

取命令实际返回的 id 作为 IDEA。先审计可用数据，再决定连续回测区间与最后约三成的样本外日期；在看收益之前用 `lab idea holdout` 登记。不要照抄 Mayne 上一轮的想法号、日期或 G0 结果。

```bash
IDEA='上一步实际返回的 id'
s03ft lab idea holdout --id "$IDEA" --start '你在回测之前选定的日期'
s03ft lab idea move --id "$IDEA" --to screening --reason 'spec frozen; data audited'
s03ft lab idea move --id "$IDEA" --to backtesting --reason 'first registered trial'
```

每换一组参数都登记一次；保留失败方案、没有信号的时间和不利时期，不根据已经看过的结果移动样本外起点。单元测试只验证工程行为，不是收益尝试。

## 数据与执行口径

按包声明下载信号周期、背景周期及用于执行诊断的细周期。由于原框架对全部白名单订阅日线作相关性计算，必须审计当前配置全部币种的信号与信息周期覆盖。不要修改生产白名单来隐藏缺口。

永续历史要检查价格、mark 与 funding_rate，不能把只下载到几个月资金费率的多年回测当作完整净收益。UTC／纽约时区切分、夏令时、节假日处理、缺失 K 线、断网和部分成交也需要检查。新代理没有历史市场回测时，VALIDATION 必须写未运行。

框架的 `strategy_exit()` 或 `take_profit_legs()` 是循环采样管理，不等于交易所静态止盈触价立即成交。实际绑定止损可能受 better_fill_policy、护栏和取整影响；以绑定后的风险算 R，不用原信号或杠杆收益率代替。

## G0 与组合主证据

```bash
s03ft research g0 --timerange '事先冻结的开发段区间'
s03ft events build --out research/events_history.json --history
s03ft research portfolio --all --idea "$IDEA" --trials base,stop_floor \
  --timerange '事先冻结的完整区间'
s03ft research verdict --idea "$IDEA"
```

这是流程形状，区间占位符必须替换。base／stop_floor 在某些策略上可能生成完全相同结果；PBO 所需实际不同候选不足时，不能宣称通过。三项压力 cost2x、delay1、stopslip 全部保留；不修改阈值、护栏或审批状态来凑通过。

不经包装器的直接细周期回测需要**仅对本次研究进程**设置历史事件与风险日志，例如：

```bash
mkdir -p research/results
RUN_DIR="$(mktemp -d research/results/pack-detail-XXXXXX)"
S03_EVENTS_REQUIRED=0 S03_EVENTS_FILE=research/events_history.json \
  S03_NEWS_FILE='' S03_RISK_LOG="$RUN_DIR/risk.jsonl" \
  freqtrade backtesting -c "$S03_FT_CONFIG" --strategy "$FW_STRATEGY" \
  --strategy-path user_data/strategies --timerange '冻结的开发段' \
  --timeframe-detail 1m --enable-protections --cache none \
  --export trades --backtest-directory "$RUN_DIR"
```

先登记这次执行口径尝试；不把独立诊断冒充组合 base，不全局关闭事件守卫。细周期必须已下载，不支持的模拟情境要保留未知。

## 状态与审批

工程包的测试通过不等于进入 validated。G0 有限抽查也不证明所有窗口没有偏差。G1–G5 的统计门槛、G6 极端情境、G7 滚动与重启一致性、G8 模拟时长和 G9 人工授权均保留为各自条件。本库不运行 `freqtrade trade`，不批准想法，不改变 dry_run。

若真正完成一轮财务检验后结论为证据不足或不通过，按目标框架登记 rejected 与具体原因；不能删掉失败记录再换名字称作新优势。

## v2 新币种与方向

配置见 [币种与多空设置](CONFIGURATION.md)。每次更改白名单、方向、成本或规则均属于新的研究范围，先登记再回测；新空头是模型推断，不能沿用 v1 多头验证。新增币种的可用历史、资金费率、最小名义金额、价格精度和维持保证金档位要重新审计。
