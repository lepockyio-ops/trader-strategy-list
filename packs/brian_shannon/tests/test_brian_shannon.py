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
from BrianShannonAVWAP import BrianShannonAVWAP, confirmed_low_avwap
from framework_base import FrameworkStrategy


def frame():
    c = np.array([100, 100, 100, 99, 98, 99, 100, 100, 99.7, 99.0, 100.8], dtype=float)
    low = np.array([99.5, 99.6, 99.7, 98.8, 97, 98.5, 99.3, 99.4, 99.3, 98.9, 99.5])
    return pd.DataFrame({"date": pd.date_range("2026-01-01", periods=len(c), freq="h", tz="UTC"),
                         "open": c - 0.1, "high": c + 0.1, "low": low, "close": c, "volume": 1.0})


def run(df, pair="BTC/USDT:USDT", trend=1):
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
    out = s.populate_indicators(df, {})
    out["trend_ok_1d"] = trend
    return s.populate_entry_trend(out, {"pair": pair})


def test_anchor_is_not_exposed_before_confirmation_and_has_correct_weight():
    out = confirmed_low_avwap(frame())
    assert out.loc[:5, "avwap"].isna().all()
    assert out.loc[6, "avwap_anchor"] == frame().date.iloc[4].timestamp()
    a = frame().iloc[4:7]
    assert out.loc[6, "avwap"] == pytest.approx(((a.high + a.low + a.close) / 3).mean())


def test_reclaim_breakout_has_absolute_stop_and_cap():
    out = run(frame())
    assert out.enter_long.sum() == 1
    row = out[out.enter_long.eq(1)].iloc[0]
    assert row.fw_stop < row.close < row.fw_entry_cap
    assert row.fw_stop == pytest.approx(out.low.iloc[-6:].min() * .999)


@pytest.mark.parametrize("pair,trend", [("BTC/USDC:USDC", 1), ("ADA/USDT:USDT", 1),
                                         ("BTC/USDT", 1), ("BTC/USDT:USDT", 0)])
def test_pair_and_trend_gates(pair, trend):
    assert run(frame(), pair, trend).enter_long.sum() == 0


def test_missing_trend_and_zero_volume_fail_closed():
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
    assert s.populate_entry_trend(s.populate_indicators(frame(), {}), {"pair": "BTC/USDT:USDT"}).enter_long.sum() == 0
    df = frame()
    df["volume"] = 0.0
    assert run(df).enter_long.sum() == 0
    assert confirmed_low_avwap(df).avwap.isna().all()


def test_every_prefix_and_future_perturbation_are_causal():
    df = frame()
    out = run(df)
    for n in range(1, len(df) + 1):
        assert_frame_equal(run(df.iloc[:n]), out.iloc[:n])
    changed = df.copy()
    changed.loc[8:, ["low", "close"]] = [50., 51.]
    assert_frame_equal(run(changed).iloc[:8], out.iloc[:8])


def test_daily_direction_needs_warmup():
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
    df = pd.DataFrame({"close": np.arange(100.) + 100})
    out = s.populate_indicators_1d(df, {})
    assert out.trend_ok.iloc[:54].sum() == 0
    assert out.trend_ok.iloc[-1] == 1


def test_exit_and_partial_take_profit():
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
    assert s.take_profit_legs(None) == [(1., 1 / 3, "shannon_first_third")]
    assert s.strategy_exit("BTC", None, None, 97, {"close": 97, "avwap": 99, "prior_low": 98}) == "shannon_structure_failed"
    assert s.strategy_exit("BTC", None, None, 98.5, {"close": 98.5, "avwap": 99, "prior_low": 98}) is None
    assert s.strategy_exit("BTC", None, None, 98, None) is None


def test_framework_callbacks_are_inherited():
    for name in ("advise_entry", "informative_pairs", "leverage", "custom_stake_amount", "custom_exit",
                 "custom_stoploss", "confirm_trade_entry", "order_filled", "adjust_trade_position"):
        assert getattr(BrianShannonAVWAP, name) is getattr(FrameworkStrategy, name)
    assert BrianShannonAVWAP.framework_params == {}
    assert set(BrianShannonAVWAP.research_stress) == {"cost2x", "delay1", "stopslip"}


# v2: explicit bearish fixtures, entry policy, plan contract and causality.
def _v2_bearish_source():
    raw = frame().copy()
    original = raw.copy()
    raw["open"], raw["close"] = 200 - original["open"], 200 - original["close"]
    raw["high"], raw["low"] = 200 - original["low"], 200 - original["high"]
    return raw


def _v2_signals(raw, mode="both", pairs=None, pair="BTC/USDT:USDT"):
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
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
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
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
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
    now = pd.Timestamp("2026-06-01 16:00Z")
    t = SimpleNamespace(open_rate=100., is_short=True, open_date_utc=now)
    row = pd.Series({"close":101.,"high_avwap":100.,"prior_high":100.5})
    assert s.strategy_exit("BTC",t,now,101.,row) is not None
    row["close"]=99.
    assert s.strategy_exit("BTC",t,now,99.,row) is None


def test_v2_short_exit_needs_both_structure_conditions():
    from types import SimpleNamespace
    s = BrianShannonAVWAP.__new__(BrianShannonAVWAP)
    t = SimpleNamespace(is_short=True)
    for avwap, prior in ((100.,102.),(102.,100.)):
        row = pd.Series({"close":101.,"high_avwap":avwap,"prior_high":prior})
        assert s.strategy_exit("BTC",t,None,101.,row) is None
