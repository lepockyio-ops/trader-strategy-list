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


@pytest.mark.parametrize("pair", ["BTC/USDT", "ADA/USDT:USDT", "ETH/USDC:USDC"])
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


# v2: explicit bearish fixtures, entry policy, plan contract and causality.
def _v2_bearish_source():
    raw = frame().copy()
    original = raw.copy()
    raw["open"], raw["close"] = 200 - original["open"], 200 - original["close"]
    raw["high"], raw["low"] = 200 - original["low"], 200 - original["high"]
    return raw


def _v2_signals(raw, mode="both", pairs=None, pair="BTC/USDT:USDT"):
    s = ImreGamsAuctionProxy.__new__(ImreGamsAuctionProxy)
    s.config = {"fw_trade_direction": mode}
    if pairs is not None:
        s.config["exchange"] = {"pair_whitelist": pairs}
    df = s.populate_indicators(raw, {})
    df["trend_ok_1d"], df["trend_short_1d"] = 0, 1
    df["bull_structure_1d"], df["last_low_1d"] = 0, 95.0
    df["bear_structure_1d"], df["last_high_1d"] = 1, 105.0
    return s.populate_entry_trend(df, {"pair": pair})


def test_v2_actual_bearish_pattern_and_plan():
    from framework_base import decode_plan
    raw = _v2_bearish_source()
    out = _v2_signals(raw)
    hits = out.loc[out.enter_short.eq(1)]
    assert len(hits) > 0
    assert (hits.fw_stop > hits.close).all() and (hits.fw_entry_cap < hits.close).all()
    assert out.enter_long.sum() == 0
    s = ImreGamsAuctionProxy.__new__(ImreGamsAuctionProxy)
    planned = s.advise_entry(s.populate_indicators(raw, {}).assign(
        trend_ok_1d=0, trend_short_1d=1, bull_structure_1d=0,
        last_low_1d=95., bear_structure_1d=1, last_high_1d=105.), {"pair":"BTC/USDT:USDT"})
    for _, row in planned.loc[planned.enter_short.eq(1)].iterrows():
        plan = decode_plan(row.enter_tag)
        assert plan["side"] == "short" and plan["stop"] > row.close and plan["cap"] < row.close


@pytest.mark.parametrize("coin", ["BTC", "ETH", "SOL", "BNB", "HYPE"])
def test_v2_five_default_pairs_and_direction_switch(coin):
    raw = _v2_bearish_source()
    pair = coin + "/USDT:USDT"
    assert _v2_signals(raw, pair=pair).enter_short.sum() > 0
    assert _v2_signals(raw, mode="short", pair=pair).enter_short.sum() > 0
    assert _v2_signals(raw, mode="long", pair=pair).enter_short.sum() == 0
    assert _v2_signals(raw, pairs=[], pair=pair).enter_short.sum() == 0


def test_v2_add_remove_pair_and_zero_volume():
    raw = _v2_bearish_source()
    pair = "ADA/USDT:USDT"
    assert _v2_signals(raw, pair=pair).enter_short.sum() == 0
    assert _v2_signals(raw, pairs=[pair], pair=pair).enter_short.sum() > 0
    raw["volume"] = 0.
    assert _v2_signals(raw).enter_short.sum() == 0


def test_v2_bearish_prefix_and_future_stability():
    raw = _v2_bearish_source()
    full = _v2_signals(raw)
    for n in (3, len(raw)//2, len(raw)-2, len(raw)-1, len(raw)):
        assert_frame_equal(_v2_signals(raw.iloc[:n]), full.iloc[:n])
    cut = len(raw)//2
    changed = raw.copy()
    changed.loc[changed.index[cut:], ["high", "low", "close"]] = [190, 10, 150]
    assert_frame_equal(_v2_signals(changed).iloc[:cut], full.iloc[:cut])


def test_v2_short_exit_is_directional():
    from types import SimpleNamespace
    s = ImreGamsAuctionProxy.__new__(ImreGamsAuctionProxy)
    now = pd.Timestamp("2026-06-01 16:00Z")
    from framework_base import encode_plan
    t = SimpleNamespace(open_rate=100., is_short=True, open_date_utc=now,
                        enter_tag=encode_plan(102.,99.9,now,"imre_mid:98",side="short"))
    assert s.strategy_exit("BTC",t,now,98.01,None) is None
    assert s.strategy_exit("BTC",t,now,98.,None) is not None
