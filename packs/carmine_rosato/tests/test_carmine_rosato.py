from datetime import datetime, timedelta, timezone
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

from CarmineRosatoReclaimProxy import CarmineRosatoReclaimProxy as S
from framework_base import FrameworkStrategy, guarded_stop


def bars():
    df = pd.DataFrame({"date": pd.date_range("2026-01-05", periods=80, freq="15min", tz="UTC"),
                       "open": 100.0, "high": 101.0, "low": 99.0,
                       "close": 100.0, "volume": 1.0})
    df.loc[60, ["open", "high", "low", "close", "volume"]] = [99.5, 101, 98, 100.5, 2]
    return df


def run(df, pair="BTC/USDT:USDT"):
    s = S.__new__(S)
    return s.populate_entry_trend(s.populate_indicators(df, {}), {"pair": pair})


def test_actual_signal_and_absolute_stop():
    out = run(bars())
    assert out.index[out.enter_long.eq(1)].tolist() == [60]
    row = out.loc[60]
    assert row.prior_support == 99
    assert row.fw_stop == pytest.approx(97.902)
    assert guarded_stop(row.close, row.fw_stop, S.__new__(S).fw) == row.fw_stop
    assert row.fw_entry_cap == pytest.approx(100.6005)


@pytest.mark.parametrize("column,value", [("volume", 1), ("low", 99), ("close", 98.5), ("high", 104)])
def test_rejection_of_missing_setup_features(column, value):
    df = bars()
    df.loc[60, column] = value
    assert run(df).enter_long.sum() == 0


def test_warmup_missing_volume_and_zero_range():
    assert run(bars().iloc[:30]).enter_long.sum() == 0
    df = bars()
    df.loc[60, "volume"] = np.nan
    assert run(df).enter_long.sum() == 0
    df.loc[60, ["open", "high", "low", "close"]] = [100, 100, 100, 100]
    assert run(df).enter_long.sum() == 0


@pytest.mark.parametrize("pair", ["BTC/USDT", "BTC/USDC:USDC", "ADA/USDT:USDT"])
def test_exact_pair_boundary(pair):
    assert run(bars(), pair).enter_long.sum() == 0


def test_prefix_and_future_perturbation():
    df = bars()
    full = run(df)
    for n in [10, 50, 60, 61, 65, 80]:
        assert_frame_equal(run(df.iloc[:n]), full.iloc[:n])
    df.loc[65:, ["high", "low", "close", "volume"]] = [200, 50, 150, 100]
    assert_frame_equal(run(df).iloc[:65], full.iloc[:65])


def test_bound_stop_target_and_time_exit():
    s = S.__new__(S)
    now = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
    t = SimpleNamespace(open_rate=100, open_date_utc=now, get_custom_data=lambda k: 98)
    assert s.strategy_exit("BTC", t, now, 103.99, None) is None
    assert s.strategy_exit("BTC", t, now, 104, None) == "carmine_proxy_2R"
    assert s.strategy_exit("BTC", t, now + timedelta(hours=8), 100, None) == "carmine_proxy_time"


def test_framework_controls_inherited():
    for name in ["advise_entry", "custom_stake_amount", "leverage", "custom_stoploss", "custom_exit",
                 "confirm_trade_entry", "order_filled", "informative_pairs", "adjust_trade_position"]:
        assert getattr(S, name) is getattr(FrameworkStrategy, name)
    assert S.framework_params == {}
    assert set(S.research_stress) == {"cost2x", "delay1", "stopslip"}


# v2: explicit bearish fixtures, entry policy, plan contract and causality.
def _v2_bearish_source():
    raw = bars().copy()
    original = raw.copy()
    raw["open"], raw["close"] = 200 - original["open"], 200 - original["close"]
    raw["high"], raw["low"] = 200 - original["low"], 200 - original["high"]
    return raw


def _v2_signals(raw, mode="both", pairs=None, pair="BTC/USDT:USDT"):
    s = S.__new__(S)
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
    s = S.__new__(S)
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
    s = S.__new__(S)
    now = pd.Timestamp("2026-06-01 16:00Z")
    t = SimpleNamespace(open_rate=100., is_short=True, get_custom_data=lambda key:102., open_date_utc=now)
    assert s.strategy_exit("BTC",t,now,100.-s.target_r*2.+.001,None) is None
    assert s.strategy_exit("BTC",t,now,100.-s.target_r*2.,None) is not None
