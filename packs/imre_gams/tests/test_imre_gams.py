from types import SimpleNamespace
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

PACK = Path(__file__).resolve().parents[1]
TARGET = Path(os.environ.get("FT_FRAMEWORK_ROOT", str(Path.cwd())))
sys.path.insert(0, str(TARGET / "user_data" / "strategies"))
sys.path.insert(0, str(PACK / "user_data" / "strategies"))
from ImreGamsAuctionProxy import ImreGamsAuctionProxy
from framework_base import FrameworkStrategy, decode_plan, encode_plan, guarded_stop


def frame():
    n = 65
    c = np.array([100 + (.1 if i % 2 else -.1) for i in range(n)])
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
                       "open": c, "close": c, "high": 102., "low": 98.5, "volume": 1.})
    df.loc[40, ["open", "close", "low", "volume"]] = [98.6, 98.75, 97.9, 2.]
    return df


def run(df, pair="BTC/USDT:USDT"):
    s = ImreGamsAuctionProxy.__new__(ImreGamsAuctionProxy)
    return s.populate_entry_trend(s.populate_indicators(df, {}), {"pair": pair})


def test_balanced_failed_downside_breakout_freezes_midpoint():
    out = run(frame())
    assert out.index[out.enter_long.eq(1)].tolist() == [40]
    row = out.loc[40]
    assert row.range_mid == 100.25
    assert row.enter_tag == "imre_mid:100.25"
    assert row.fw_stop < row.close < row.fw_entry_cap
    s = ImreGamsAuctionProxy.__new__(ImreGamsAuctionProxy)
    assert guarded_stop(row.close, row.fw_stop, s.fw) == row.fw_stop


@pytest.mark.parametrize("change", ["no_sweep", "low_volume", "little_room", "trending"])
def test_rejects_mismatched_environment_and_entry(change):
    df = frame()
    if change == "no_sweep":
        df.loc[40, "low"] = 98.5
    elif change == "low_volume":
        df.loc[40, "volume"] = 1
    elif change == "little_room":
        df.loc[40, "close"] = 100.2
    else:
        df.loc[:39, "close"] = np.linspace(99, 101, 40)
    assert run(df).enter_long.sum() == 0


@pytest.mark.parametrize("pair", ["BTC/USDT", "SOL/USDT:USDT", "ETH/USDC:USDC"])
def test_pair_gate(pair):
    assert run(frame(), pair).enter_long.sum() == 0


def test_short_history_and_nan_are_not_permission():
    assert run(frame().iloc[:24]).enter_long.sum() == 0
    df = frame()
    df.loc[:40, "volume"] = np.nan
    assert run(df).enter_long.sum() == 0


def test_every_prefix_and_future_change_are_causal():
    df = frame()
    out = run(df)
    for n in (1, 24, 25, 40, 41, 65):
        assert_frame_equal(run(df.iloc[:n]), out.iloc[:n])
    changed = df.copy()
    changed.loc[45:, "high"] = 500
    assert_frame_equal(run(changed).iloc[:45], out.iloc[:45])


def test_target_is_from_order_plan_not_new_range_and_time_limit():
    s = ImreGamsAuctionProxy.__new__(ImreGamsAuctionProxy)
    opened = pd.Timestamp("2026-01-01 00:00Z")
    tag = encode_plan(97.8, 99, opened, "imre_mid:100.25")
    t = SimpleNamespace(enter_tag=tag, open_rate=98.75, open_date_utc=opened)
    assert decode_plan(tag)["user"] == "imre_mid:100.25"
    assert s.strategy_exit("BTC", t, opened, 100.24, {"range_mid": 90}) is None
    assert s.strategy_exit("BTC", t, opened, 100.25, {"range_mid": 900}) == "imre_frozen_midpoint"
    assert s.strategy_exit("BTC", t, opened + pd.Timedelta(hours=24), 99, None) == "imre_example_time_limit"
    t.enter_tag = "malformed"
    assert s.strategy_exit("BTC", t, opened, 101, None) is None


def test_risk_and_order_callbacks_not_overridden():
    for name in ("advise_entry", "informative_pairs", "leverage", "custom_stake_amount", "custom_exit",
                 "custom_stoploss", "confirm_trade_entry", "order_filled", "adjust_trade_position"):
        assert getattr(ImreGamsAuctionProxy, name) is getattr(FrameworkStrategy, name)
    assert ImreGamsAuctionProxy.framework_params == {}
    assert set(ImreGamsAuctionProxy.research_stress) == {"cost2x", "delay1", "stopslip"}
