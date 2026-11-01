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
from PeterBrandtRectangle import PeterBrandtRectangle
from framework_base import FrameworkStrategy, guarded_stop


def frame(n=65):
    df = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=n, freq="D", tz="UTC"),
                       "open": 101., "high": 102., "low": 100., "close": 101., "volume": 1.})
    df.loc[50, ["close", "high"]] = [102.5, 102.6]
    return df


def run(df, pair="BTC/USDT:USDT"):
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
    return s.populate_entry_trend(s.populate_indicators(df, {}), {"pair": pair})


def trade(opened="2026-01-05 00:00Z", stop=98):
    return SimpleNamespace(open_rate=100., open_date_utc=pd.Timestamp(opened), get_custom_data=lambda k: stop)


def test_rectangle_breakout_and_stop_contract():
    out = run(frame())
    assert out.index[out.enter_long.eq(1)].tolist() == [50]
    row = out.loc[50]
    assert row.box_top == 102 and row.box_bottom == 100
    assert row.fw_stop == pytest.approx(99.9)
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
    assert guarded_stop(row.close, row.fw_stop, s.fw) == row.fw_stop


def test_wide_and_single_touch_rectangles_are_rejected():
    df = frame()
    df.loc[:49, "high"] = 120
    df.loc[50, ["high", "close"]] = [122, 121]
    assert run(df).enter_long.sum() == 0
    df = frame()
    df.loc[20, "high"] = 104
    df.loc[50, ["high", "close"]] = [105, 104.8]
    assert run(df).enter_long.sum() == 0


@pytest.mark.parametrize("pair", ["ADA/USDT:USDT", "BTC/USDT", "ETH/USDC:USDC"])
def test_only_exact_supported_pairs(pair):
    assert run(frame(), pair).enter_long.sum() == 0


def test_warmup_and_zero_volume():
    assert run(frame().iloc[:42]).enter_long.sum() == 0
    df = frame()
    df["volume"] = 0
    assert run(df).enter_long.sum() == 0


def test_prefixes_and_future_data_do_not_change_prior_signals():
    df = frame()
    out = run(df)
    for n in (10, 42, 43, 50, 51, 65):
        assert_frame_equal(run(df.iloc[:n]), out.iloc[:n])
    changed = df.copy()
    changed.loc[55:, "low"] = 40
    assert_frame_equal(run(changed).iloc[:55], out.iloc[:55])


def test_two_full_losing_days_only_after_actual_entry():
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
    row = {"date": pd.Timestamp("2026-01-06 00:00Z"), "close": 99, "prior_close": 99}
    assert s.strategy_exit("BTC", trade("2026-01-05 12:00Z"), None, 99, row) is None
    row["date"] = pd.Timestamp("2026-01-07 00:00Z")
    assert s.strategy_exit("BTC", trade("2026-01-05 12:00Z"), None, 99, row) == "brandt_two_losing_days"


def test_friday_check_and_bound_stop_target():
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
    row = {"date": pd.Timestamp("2026-01-09 00:00Z"), "close": 99, "prior_close": 101}
    assert s.strategy_exit("BTC", trade(), None, 99, row) == "brandt_losing_utc_friday"
    assert s.strategy_exit("BTC", trade(), None, 106, None) == "brandt_example_3R"
    assert s.strategy_exit("BTC", trade(stop=97), None, 106, None) is None
    assert s.strategy_exit("BTC", trade(stop=None), None, 106, None) is None


def test_framework_callbacks_and_stress_are_inherited():
    for name in ("advise_entry", "informative_pairs", "leverage", "custom_stake_amount", "custom_exit",
                 "custom_stoploss", "confirm_trade_entry", "order_filled", "adjust_trade_position"):
        assert getattr(PeterBrandtRectangle, name) is getattr(FrameworkStrategy, name)
    assert PeterBrandtRectangle.framework_params == {}
    assert set(PeterBrandtRectangle.research_stress) == {"cost2x", "delay1", "stopslip"}


# v2: explicit bearish fixtures, entry policy, plan contract and causality.
def _v2_bearish_source():
    raw = frame().copy()
    original = raw.copy()
    raw["open"], raw["close"] = 200 - original["open"], 200 - original["close"]
    raw["high"], raw["low"] = 200 - original["low"], 200 - original["high"]
    return raw


def _v2_signals(raw, mode="both", pairs=None, pair="BTC/USDT:USDT"):
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
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
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
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
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
    now = pd.Timestamp("2026-06-01 16:00Z")
    t = SimpleNamespace(open_rate=100., is_short=True, get_custom_data=lambda key:102., open_date_utc=now)
    assert s.strategy_exit("BTC",t,now,100.-s.target_r*2.+.001,None) is None
    assert s.strategy_exit("BTC",t,now,100.-s.target_r*2.,None) is not None


def test_v2_short_two_losing_days_and_friday():
    s = PeterBrandtRectangle.__new__(PeterBrandtRectangle)
    t = trade("2026-06-01 00:00Z", stop=102.)
    t.is_short = True
    now = pd.Timestamp("2026-06-04 00:00Z")
    row = pd.Series({"date":pd.Timestamp("2026-06-03 00:00Z"),"close":101.,"prior_close":100.5})
    assert s.strategy_exit("BTC",t,now,101.,row) == "brandt_two_losing_days"
    row["prior_close"] = 99.
    assert s.strategy_exit("BTC",t,now,101.,row) is None
    row["date"] = pd.Timestamp("2026-06-05 00:00Z")
    assert s.strategy_exit("BTC",t,now,101.,row) == "brandt_losing_utc_friday"
    row["close"] = 99.
    assert s.strategy_exit("BTC",t,now,99.,row) is None
