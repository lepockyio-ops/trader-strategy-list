"""Load each real plugin through Freqtrade's actual analysis pipeline and risk base."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from freqtrade.enums import CandleType, RunMode
from framework_base import FrameworkStrategy, decode_plan

ROOT = Path(__file__).resolve().parents[1]


def entries():
    return json.loads((ROOT / "manifest.json").read_text("utf-8"))["packs"]


def candles(periods, freq):
    date = pd.date_range(end="2026-10-01", periods=periods, freq=freq, tz="UTC")
    t = np.arange(periods)
    close = 100 + 0.015 * t + 2 * np.sin(t / 11)
    return pd.DataFrame({"date": date, "open": close - 0.1, "close": close,
                         "high": close + 0.4, "low": close - 0.5,
                         "volume": 1000 + 100 * np.cos(t / 7)})


@pytest.mark.parametrize("item", entries(), ids=lambda x: x["slug"])
def test_real_analysis_and_plan_contract(item):
    source = ROOT / "packs" / item["slug"] / item["strategy_file"]
    module_spec = importlib.util.spec_from_file_location(item["class_name"], source)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    cls = getattr(module, item["class_name"])
    strategy = cls({"stake_currency": "USDT", "candle_type_def": CandleType.FUTURES,
                    "runmode": RunMode.BACKTEST})
    strategy.dp = SimpleNamespace(
        runmode=SimpleNamespace(value="backtest"),
        market=lambda pair: {"base": pair.split("/")[0], "quote": "USDT"},
        current_whitelist=lambda: ["BTC/USDT:USDT", "ETH/USDT:USDT"],
        get_pair_dataframe=lambda *args: candles(650, "D"),
    )
    interval = {"1h": "h", "4h": "4h", "1d": "D", "5m": "5min", "15m": "15min"}[strategy.timeframe]
    data = candles(max(650, strategy.startup_candle_count + 50), interval)
    result = strategy.advise_entry(strategy.advise_indicators(data, {"pair": "BTC/USDT:USDT"}),
                                   {"pair": "BTC/USDT:USDT"})
    assert len(result) == len(data)
    assert result["enter_long"].fillna(0).isin([0, 1]).all()
    for _, row in result[result.enter_long.eq(1)].iterrows():
        plan = decode_plan(row.enter_tag)
        assert plan is not None and np.isfinite(plan["stop"])
        assert 0 < plan["stop"] < row.close
        assert len(row.enter_tag) <= 255
    for name in ("custom_stake_amount", "custom_stoploss", "confirm_trade_entry", "leverage",
                 "order_filled", "custom_exit", "adjust_trade_position", "advise_entry", "bot_loop_start"):
        assert getattr(cls, name) is getattr(FrameworkStrategy, name)
    assert result["enter_short"].fillna(0).isin([0, 1]).all()
    for _, row in result[result.enter_short.eq(1)].iterrows():
        plan = decode_plan(row.enter_tag)
        assert plan is not None and plan["side"] == "short" and plan["stop"] > row.close
    assert strategy.can_short is True and strategy.framework_params == {}
    assert set(strategy.research_stress) == {"cost2x", "delay1", "stopslip"}
