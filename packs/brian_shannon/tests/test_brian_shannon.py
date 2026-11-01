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


@pytest.mark.parametrize("pair,trend", [("BTC/USDC:USDC", 1), ("SOL/USDT:USDT", 1),
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
