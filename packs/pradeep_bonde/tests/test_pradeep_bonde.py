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


@pytest.mark.parametrize("pair",["SOL/USDT:USDT","BTC/USDC:USDC","BTC/USDT"])
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
