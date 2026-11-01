"""Causal timing, weekly state, signal contract and inherited execution boundaries."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from freqtrade.strategy import merge_informative_pair
from freqtrade.enums import CandleType, RunMode

PACK = Path(__file__).resolve().parents[1]
TARGET = Path(os.environ.get("FT_FRAMEWORK_ROOT", str(Path.cwd())))
sys.path.insert(0, str(TARGET / "user_data" / "strategies"))
sys.path.insert(0, str(PACK / "user_data" / "strategies"))
from TraderMayneWeeklyHL import TraderMayneWeeklyHL, confirmed_structure  # noqa: E402
from framework_base import FrameworkStrategy, decode_plan, guarded_stop  # noqa: E402


def strategy():
    return TraderMayneWeeklyHL.__new__(TraderMayneWeeklyHL)


def daily():
    close = np.array([100, 102, 105, 102, 100, 98, 100, 104, 110, 106,
                      104, 101, 104, 107, 115, 111, 108, 105, 109, 116], dtype=float)
    return pd.DataFrame({"date": pd.date_range("2026-09-01", periods=len(close), freq="D", tz="UTC"),
                         "open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": 1.0})


def hourly(start="2026-10-05", n=24 * 8):
    df = pd.DataFrame({"date": pd.date_range(start, periods=n, freq="h", tz="UTC"),
                       "open": 100.0, "high": 100.2, "low": 99.8,
                       "close": 100.0, "volume": 1.0})
    df.loc[0, "low"] = 99.0
    # Two separated breakouts, so the weekly-first filter has something to reject.
    for i, price in ((12, 100.7), (30, 102.0)):
        df.loc[i, ["close", "high"]] = [price, price + 0.1]
    return df


def signals(df, bull=1, anchor=95.0, pair="BTC/USDT:USDT"):
    s = strategy()
    frame = s.populate_indicators(df, {})
    frame["bull_structure_1d"] = bull
    frame["last_low_1d"] = anchor
    return s.populate_entry_trend(frame, {"pair": pair})


def test_pivot_appears_only_after_right_bars_close():
    df = confirmed_structure(daily())
    assert pd.isna(df.loc[2, "pivot_high"])
    assert df.loc[4, "pivot_high"] == 106
    assert df.loc[7, "pivot_low"] == 97
    assert df.loc[12, "bull_structure"] == 0
    assert df.loc[13, "bull_structure"] == 1
    assert df.loc[13, "last_low"] == 100


def test_equal_extrema_are_not_multiple_pivots():
    df = daily()
    df["high"], df["low"] = 101.0, 99.0
    out = confirmed_structure(df)
    assert out["pivot_high"].isna().all() and out["pivot_low"].isna().all()
    assert out["bull_structure"].sum() == 0


def test_daily_every_prefix_matches_full_history():
    df = daily()
    out = confirmed_structure(df)
    for n in range(1, len(df) + 1):
        assert_frame_equal(confirmed_structure(df.iloc[:n]), out.iloc[:n])


def test_daily_information_becomes_visible_only_on_close():
    info = confirmed_structure(daily())
    hours = hourly("2026-09-13", 48)
    out = merge_informative_pair(hours, info, "1h", "1d", ffill=True)
    # Sep 14 daily HL confirms at the end of Sep 14, not at its midnight open.
    assert out.loc[out.date == pd.Timestamp("2026-09-14 22:00Z"), "bull_structure_1d"].item() == 0
    assert out.loc[out.date == pd.Timestamp("2026-09-14 23:00Z"), "bull_structure_1d"].item() == 1


def test_real_informative_decorator_analysis_pipeline():
    s = TraderMayneWeeklyHL({"stake_currency": "USDT", "candle_type_def": CandleType.FUTURES,
                             "runmode": RunMode.BACKTEST})
    s.dp = SimpleNamespace(
        market=lambda pair: {"base": "BTC", "quote": "USDT"},
        get_pair_dataframe=lambda *args: daily(),
        current_whitelist=lambda: ["BTC/USDT:USDT", "ETH/USDT:USDT"],
    )
    out = s.advise_indicators(hourly("2026-09-13", 48), {"pair": "BTC/USDT:USDT"})
    assert "week_low" in out and "bull_structure_1d" in out
    assert out.loc[out.date == pd.Timestamp("2026-09-14 22:00Z"), "bull_structure_1d"].item() == 0
    assert out.loc[out.date == pd.Timestamp("2026-09-14 23:00Z"), "bull_structure_1d"].item() == 1
    assert ("ETH/USDT:USDT", "1d") in s.informative_pairs()


def test_one_candidate_per_pair_per_week_with_absolute_stop():
    out = signals(hourly())
    assert out.index[out.enter_long.eq(1)].tolist() == [12]
    row = out.loc[12]
    assert row.fw_stop == pytest.approx(99 * 0.999)
    assert row.fw_entry_cap == pytest.approx(100.7 * 1.001)
    assert guarded_stop(row.close, row.fw_stop, strategy().fw) == row.fw_stop


@pytest.mark.parametrize("bull,anchor,pair", [(0, 95, "BTC/USDT:USDT"),
                                             (1, 99, "BTC/USDT:USDT"),
                                             (1, 95, "ADA/USDT:USDT"),
                                             (1, 95, "BTC/USDC:USDC"),
                                             (1, 95, "BTC/USDT")])
def test_no_permission_without_daily_structure_or_allowed_pair(bull, anchor, pair):
    assert signals(hourly(), bull, anchor, pair).enter_long.sum() == 0


def test_missing_daily_data_is_fail_closed():
    s = strategy()
    out = s.populate_entry_trend(s.populate_indicators(hourly(), {}), {"pair": "BTC/USDT:USDT"})
    assert out.enter_long.sum() == 0


def test_midweek_history_does_not_invent_week_start():
    out = signals(hourly("2026-10-06", 72))
    assert out.enter_long.sum() == 0


def test_week_reset_and_candidate_budget_reset():
    df = hourly(n=24 * 9)
    df.loc[24 * 7 + 12, ["high", "close"]] = [101.0, 100.8]
    out = signals(df)
    assert out.index[out.enter_long.eq(1)].tolist() == [12, 24 * 7 + 12]
    assert out.loc[24 * 7, "week_low"] == 99.8


def test_wednesday_last_bar_and_thursday_are_excluded():
    df = hourly(n=120)
    df.loc[:, ["close", "high"]] = [100.0, 100.2]
    df.loc[71, ["close", "high"]] = [101, 101.1]
    df.loc[83, ["close", "high"]] = [102, 102.1]
    assert signals(df).enter_long.sum() == 0


def test_zero_volume_and_no_pullback_are_excluded():
    df = hourly()
    df["volume"] = 0
    assert signals(df).enter_long.sum() == 0
    df = hourly()
    df["low"] = 100.0
    assert signals(df).enter_long.sum() == 0


def test_all_hourly_prefixes_match_and_future_changes_do_not_repaint():
    df = hourly()
    full = signals(df)
    for n in (8, 12, 13, 30, 31, 72, 100, 168, len(df)):
        assert_frame_equal(signals(df.iloc[:n]), full.iloc[:n])
    changed = df.copy()
    changed.loc[50:, "low"] = 50
    assert_frame_equal(signals(changed).iloc[:50], full.iloc[:50])


def test_parent_encodes_signal_stop_not_a_later_week_low():
    s = strategy()
    s.dp = SimpleNamespace(runmode=SimpleNamespace(value="backtest"))
    # advise_entry expects already-merged informative columns.
    df = s.populate_indicators(hourly(), {})
    df["bull_structure_1d"], df["last_low_1d"] = 1, 95.0
    out = s.advise_entry(df, {"pair": "BTC/USDT:USDT"})
    plan = decode_plan(out.loc[12, "enter_tag"])
    assert plan["stop"] == pytest.approx(out.loc[12, "fw_stop"])
    assert plan["user"] == "mayne_weekly_hl_v1"


def test_target_uses_bound_stop_and_no_leverage_multiplier():
    s = strategy()
    trade = SimpleNamespace(open_rate=100, leverage=7, get_custom_data=lambda key: 98)
    assert s.strategy_exit("BTC", trade, None, 103.99, None) is None
    assert s.strategy_exit("BTC", trade, None, 104, None) == "mayne_2R"
    trade.get_custom_data = lambda key: 97  # Framework widened stop: new actual R is 3.
    assert s.strategy_exit("BTC", trade, None, 104, None) is None
    assert s.strategy_exit("BTC", trade, None, 106, None) == "mayne_2R"


@pytest.mark.parametrize("stop", [None, np.nan, 100, 101])
def test_target_does_not_invent_a_stop(stop):
    t = SimpleNamespace(open_rate=100, get_custom_data=lambda key: stop)
    assert strategy().strategy_exit("BTC", t, None, 110, None) is None


def test_no_framework_risk_callbacks_overridden():
    for name in ("advise_entry", "informative_pairs", "custom_stake_amount", "leverage",
                 "confirm_trade_entry", "custom_stoploss", "order_filled", "custom_exit",
                 "adjust_trade_position", "check_entry_timeout", "bot_loop_start"):
        assert getattr(TraderMayneWeeklyHL, name) is getattr(FrameworkStrategy, name)
    assert strategy().framework_params == {}
    assert strategy().take_profit_legs(None) == []
    assert set(strategy().research_stress) == {"cost2x", "delay1", "stopslip"}


# v2: explicit bearish fixtures, entry policy, plan contract and causality.
def _v2_bearish_source():
    raw = hourly().copy()
    original = raw.copy()
    raw["open"], raw["close"] = 200 - original["open"], 200 - original["close"]
    raw["high"], raw["low"] = 200 - original["low"], 200 - original["high"]
    return raw


def _v2_signals(raw, mode="both", pairs=None, pair="BTC/USDT:USDT"):
    s = TraderMayneWeeklyHL.__new__(TraderMayneWeeklyHL)
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
    s = TraderMayneWeeklyHL.__new__(TraderMayneWeeklyHL)
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
    s = TraderMayneWeeklyHL.__new__(TraderMayneWeeklyHL)
    now = pd.Timestamp("2026-06-01 16:00Z")
    t = SimpleNamespace(open_rate=100., is_short=True, get_custom_data=lambda key:102., open_date_utc=now)
    assert s.strategy_exit("BTC",t,now,100.-s.target_r*2.+.001,None) is None
    assert s.strategy_exit("BTC",t,now,100.-s.target_r*2.,None) is not None
