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


@pytest.mark.parametrize("pair", ["BTC/USDT", "BTC/USDC:USDC", "SOL/USDT:USDT"])
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
