from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import os
import sys
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

PACK = Path(__file__).resolve().parents[1]
TARGET = Path(os.environ.get("FT_FRAMEWORK_ROOT", str(Path.cwd())))
sys.path.insert(0, str(TARGET / "user_data" / "strategies"))
sys.path.insert(0, str(PACK / "user_data" / "strategies"))

from ChrisCreamerFailedAuctionProxy import ChrisCreamerFailedAuctionProxy as S
from framework_base import FrameworkStrategy, encode_plan


def bars():
    df = pd.DataFrame({"date": pd.date_range("2026-01-05", periods=70, freq="5min", tz="UTC"),
                       "open": 100.5, "high": 102.0, "low": 100.0,
                       "close": 100.5, "volume": 1.0})
    df.loc[40, ["open", "high", "low", "close", "volume"]] = [100.1, 100.15, 99.9, 99.95, 2]
    df.loc[41, ["open", "high", "low", "close", "volume"]] = [99.95, 100.3, 99.92, 100.2, 1.5]
    return df


def run(df, pair="ETH/USDT:USDT"):
    s = S.__new__(S)
    return s.populate_entry_trend(s.populate_indicators(df, {}), {"pair": pair})


def test_two_stage_signal_and_original_box_target():
    out = run(bars())
    assert out.index[out.enter_long.eq(1)].tolist() == [41]
    r = out.loc[41]
    assert r.box_low == 100 and r.box_high == 102 and r.box_mid == 101
    assert r.fw_stop == pytest.approx(99.8001)
    assert r.enter_tag == "cc_mid:101"


@pytest.mark.parametrize("row,column,value", [(40, "close", 100.1), (41, "close", 100.1),
                                             (40, "volume", 1.0), (41, "volume", 0.0)])
def test_missing_failure_or_takeover_rejects(row, column, value):
    df = bars()
    df.loc[row, column] = value
    assert run(df).enter_long.sum() == 0


def test_no_room_and_unbalanced_box_reject():
    df = bars()
    df.loc[41, ["high", "close"]] = [100.9, 100.8]
    assert run(df).enter_long.sum() == 0
    df = bars()
    df.loc[:39, "high"] = 104
    assert run(df).enter_long.sum() == 0


def test_warmup_and_wrong_pair():
    assert run(bars().iloc[:20]).enter_long.sum() == 0
    assert run(bars(), "BTC/USDC:USDC").enter_long.sum() == 0


def test_prefix_and_future_perturbation():
    df = bars()
    full = run(df)
    for n in [10, 40, 41, 42, 50, 70]:
        assert_frame_equal(run(df.iloc[:n]), full.iloc[:n])
    df.loc[50:, ["high", "low", "close"]] = [200, 50, 150]
    assert_frame_equal(run(df).iloc[:50], full.iloc[:50])


def test_exit_uses_stored_target_not_latest_row():
    now = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)
    tag = encode_plan(99.8, 100.3, now, "cc_mid:101")
    t = SimpleNamespace(open_rate=100.2, enter_tag=tag, open_date_utc=now)
    s = S.__new__(S)
    assert s.strategy_exit("BTC", t, now, 100.99, {"box_mid": 100.5}) is None
    assert s.strategy_exit("BTC", t, now, 101, {"box_mid": 200}) == "creamer_proxy_mid"
    assert s.strategy_exit("BTC", t, now + timedelta(minutes=60), 100.5, None) == "creamer_proxy_time"
    t.enter_tag = "unbound"
    assert s.strategy_exit("BTC", t, now, 110, None) is None


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
    from framework_base import encode_plan
    t = SimpleNamespace(open_rate=100., is_short=True, open_date_utc=now,
                        enter_tag=encode_plan(102.,99.9,now,"cc_mid:98",side="short"))
    assert s.strategy_exit("BTC",t,now,98.01,None) is None
    assert s.strategy_exit("BTC",t,now,98.,None) is not None
