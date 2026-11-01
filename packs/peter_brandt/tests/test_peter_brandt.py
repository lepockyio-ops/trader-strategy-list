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


@pytest.mark.parametrize("pair", ["SOL/USDT:USDT", "BTC/USDT", "ETH/USDC:USDC"])
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
