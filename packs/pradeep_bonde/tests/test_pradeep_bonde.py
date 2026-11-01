"""Behavior tests against the real target framework and Freqtrade dependency."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
PACK = Path(__file__).resolve().parents[1]
TARGET = Path(os.environ.get("FT_FRAMEWORK_ROOT", str(Path.cwd())))
sys.path.insert(0, str(TARGET / "user_data" / "strategies"))
sys.path.insert(0, str(PACK / "user_data" / "strategies"))
from PradeepBondeBurst import PradeepBondeBurst
from framework_base import FrameworkStrategy,decode_plan,guarded_stop


def candles(n,freq):
    return pd.DataFrame({"date":pd.date_range("2025-01-01",periods=n,freq=freq,tz="UTC"),
        "open":100.,"close":100.,"high":100.2,"low":99.8,"volume":1.})


def fixture():
    df = candles(80, "h")
    c = np.r_[np.full(60,100.0), np.linspace(100,103.5,19), 105.0]
    df["open"],df["close"],df["high"],df["low"] = c-0.1,c,c+0.2,c-0.2
    df.loc[79,"volume"] = 3
    return df


def run(df,pair="BTC/USDT:USDT"):
    s=PradeepBondeBurst.__new__(PradeepBondeBurst)
    df=s.populate_indicators(df,{})
    df["trend_ok_1d"] = 1
    return s.populate_entry_trend(df,{"pair":pair})


def test_positive_signal_has_absolute_executable_stop():
    row=run(fixture()).iloc[-1]
    assert row.enter_long==1
    assert 0<row.fw_stop<row.close<row.fw_entry_cap
    assert guarded_stop(row.close,row.fw_stop,PradeepBondeBurst.__new__(PradeepBondeBurst).fw) is not None


@pytest.mark.parametrize("pair",["ADA/USDT:USDT","BTC/USDC:USDC","BTC/USDT"])
def test_only_exact_allowed_products(pair):
    assert run(fixture(),pair).enter_long.sum()==0


def test_zero_volume_and_short_history_do_not_signal():
    df=fixture();df["volume"]=0
    assert run(df).enter_long.sum()==0
    assert run(fixture().iloc[:3]).enter_long.sum()==0


def test_breakout_without_required_24h_momentum_is_excluded():
    df=fixture()
    df.loc[79,["open","close","high","low"]]=[103.5,103.8,104,103.4]
    assert run(df).iloc[-1].enter_long==0


def test_prefix_stability_and_future_perturbation():
    df=fixture();full=run(df)
    for n in (3,len(df)//2,len(df)-2,len(df)-1,len(df)):
        assert_frame_equal(run(df.iloc[:n]),full.iloc[:n])
    changed=df.copy();cut=len(df)-10
    changed.loc[cut:,["close","high","low"]]=[200,201,50]
    assert_frame_equal(run(changed).iloc[:cut],full.iloc[:cut])


def test_parent_owns_risk_and_persists_plan():
    s=PradeepBondeBurst.__new__(PradeepBondeBurst)
    for name in ("advise_entry","custom_stake_amount","leverage","confirm_trade_entry","order_filled", "custom_stoploss","custom_exit","adjust_trade_position","check_entry_timeout","bot_loop_start", "informative_pairs"):
        assert getattr(PradeepBondeBurst,name) is getattr(FrameworkStrategy,name)
    assert s.framework_params=={}
    assert set(s.research_stress)=={"cost2x","delay1","stopslip"}
    s.dp=SimpleNamespace(runmode=SimpleNamespace(value="backtest"))
    df=s.populate_indicators(fixture(),{})
    df["trend_ok_1d"] = 1
    out=s.advise_entry(df,{"pair":"BTC/USDT:USDT"})
    row=out.iloc[-1];plan=decode_plan(row.enter_tag)
    assert plan["stop"]==pytest.approx(row.fw_stop)
    assert plan["cap"]==pytest.approx(row.fw_entry_cap)


def test_exit_contract():
    s=PradeepBondeBurst.__new__(PradeepBondeBurst)
    assert s.take_profit_legs(None) == [(2.0, 0.8, "bonde_2R_eighty")]
    assert s.strategy_exit("BTC",None,None,100,pd.Series({"close":99,"exit_sma":100})) is not None
    assert s.strategy_exit("BTC",None,None,100,pd.Series({"close":101,"exit_sma":100})) is None
    assert s.strategy_exit("BTC",None,None,100,None) is None


def test_missing_higher_timeframe_is_closed():
    s=PradeepBondeBurst.__new__(PradeepBondeBurst)
    out=s.populate_entry_trend(s.populate_indicators(fixture(),{}),{"pair":"BTC/USDT:USDT"})
    assert out.enter_long.sum()==0


def test_daily_filter_uses_only_available_prefixes():
    s=PradeepBondeBurst.__new__(PradeepBondeBurst)
    df=candles(260,"D")
    df["close"]=np.linspace(80,140,len(df))
    full=s.populate_indicators_1d(df,{})
    for n in (20,54,100,220,260):
        assert_frame_equal(s.populate_indicators_1d(df.iloc[:n],{}),full.iloc[:n])


# v2: explicit bearish fixtures, entry policy, plan contract and causality.
def _v2_bearish_source():
    raw = fixture().copy()
    original = raw.copy()
    raw["open"], raw["close"] = 200 - original["open"], 200 - original["close"]
    raw["high"], raw["low"] = 200 - original["low"], 200 - original["high"]
    return raw


def _v2_signals(raw, mode="both", pairs=None, pair="BTC/USDT:USDT"):
    s = PradeepBondeBurst.__new__(PradeepBondeBurst)
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
    s = PradeepBondeBurst.__new__(PradeepBondeBurst)
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
    s = PradeepBondeBurst.__new__(PradeepBondeBurst)
    now = pd.Timestamp("2026-06-01 16:00Z")
    t = SimpleNamespace(open_rate=100., is_short=True, open_date_utc=now)
    row = pd.Series({"close":101.,"exit_sma":100.})
    assert s.strategy_exit("BTC",t,now,101.,row) is not None
    row["close"]=99.
    assert s.strategy_exit("BTC",t,now,99.,row) is None
