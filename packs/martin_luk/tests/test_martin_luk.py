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
from MartinLukPullback import MartinLukPullback
from framework_base import FrameworkStrategy,decode_plan,guarded_stop


def candles(n,freq):
    return pd.DataFrame({"date":pd.date_range("2025-01-01",periods=n,freq=freq,tz="UTC"),
        "open":100.,"close":100.,"high":100.2,"low":99.8,"volume":1.})


def fixture():
    df = candles(80, "h")
    df.loc[78, ["close", "high", "low"]] = [99.8, 100.1, 99.4]
    df.loc[79, ["open", "close", "high", "low"]] = [100, 100.8, 101, 99.8]
    return df


def run(df,pair="BTC/USDT:USDT"):
    s=MartinLukPullback.__new__(MartinLukPullback)
    df=s.populate_indicators(df,{})
    df["trend_ok_1d"] = 1
    return s.populate_entry_trend(df,{"pair":pair})


def test_positive_signal_has_absolute_executable_stop():
    row=run(fixture()).iloc[-1]
    assert row.enter_long==1
    assert 0<row.fw_stop<row.close<row.fw_entry_cap
    assert guarded_stop(row.close,row.fw_stop,MartinLukPullback.__new__(MartinLukPullback).fw) is not None


@pytest.mark.parametrize("pair",["SOL/USDT:USDT","BTC/USDC:USDC","BTC/USDT"])
def test_only_exact_allowed_products(pair):
    assert run(fixture(),pair).enter_long.sum()==0


def test_zero_volume_and_short_history_do_not_signal():
    df=fixture();df["volume"]=0
    assert run(df).enter_long.sum()==0
    assert run(fixture().iloc[:3]).enter_long.sum()==0


def test_no_pullback_is_not_a_recovery_signal():
    df=fixture()
    df.loc[78,["open","close","high","low"]]=[100.1,100.1,100.2,100.05]
    assert run(df).iloc[-1].enter_long==0


def test_prefix_stability_and_future_perturbation():
    df=fixture();full=run(df)
    for n in (3,len(df)//2,len(df)-2,len(df)-1,len(df)):
        assert_frame_equal(run(df.iloc[:n]),full.iloc[:n])
    changed=df.copy();cut=len(df)-10
    changed.loc[cut:,["close","high","low"]]=[200,201,50]
    assert_frame_equal(run(changed).iloc[:cut],full.iloc[:cut])


def test_parent_owns_risk_and_persists_plan():
    s=MartinLukPullback.__new__(MartinLukPullback)
    for name in ("advise_entry","custom_stake_amount","leverage","confirm_trade_entry","order_filled", "custom_stoploss","custom_exit","adjust_trade_position","check_entry_timeout","bot_loop_start", "informative_pairs"):
        assert getattr(MartinLukPullback,name) is getattr(FrameworkStrategy,name)
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
    s=MartinLukPullback.__new__(MartinLukPullback)
    t = SimpleNamespace(open_rate=100, get_custom_data=lambda key:98)
    assert s.strategy_exit("BTC",t,None,105.99,None) is None
    assert s.strategy_exit("BTC",t,None,106,None) == "luk_3R"
    t.get_custom_data=lambda key:97
    assert s.strategy_exit("BTC",t,None,106,None) is None
    assert s.strategy_exit("BTC",t,None,109,None) is not None
    for invalid in (None,np.nan,100):
        t.get_custom_data=lambda key:invalid
        assert s.strategy_exit("BTC",t,None,110,None) is None


def test_missing_higher_timeframe_is_closed():
    s=MartinLukPullback.__new__(MartinLukPullback)
    out=s.populate_entry_trend(s.populate_indicators(fixture(),{}),{"pair":"BTC/USDT:USDT"})
    assert out.enter_long.sum()==0


def test_daily_filter_uses_only_available_prefixes():
    s=MartinLukPullback.__new__(MartinLukPullback)
    df=candles(260,"D")
    df["close"]=np.linspace(80,140,len(df))
    full=s.populate_indicators_1d(df,{})
    for n in (20,54,100,220,260):
        assert_frame_equal(s.populate_indicators_1d(df.iloc[:n],{}),full.iloc[:n])
