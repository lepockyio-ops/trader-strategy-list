from datetime import datetime, timezone
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

from AndreaCimitanORB import AndreaCimitanORB as S
from framework_base import FrameworkStrategy


def session(day="2026-06-01"):
    start = pd.Timestamp(day + " 07:30", tz="America/New_York").tz_convert("UTC")
    df = pd.DataFrame({"date": pd.date_range(start, periods=120, freq="5min"),
                       "open": 100.0, "high": 100.2, "low": 99.8,
                       "close": 100.0, "volume": 1.0})
    df.loc[24:26, "low"] = 99.0
    df.loc[27, ["high", "close", "volume"]] = [101.2, 101, 2]
    df.loc[35, ["high", "close", "volume"]] = [102.2, 102, 3]
    return df


def run(df, pair="BTC/USDT:USDT"):
    s = S.__new__(S)
    return s.populate_entry_trend(s.populate_indicators(df, {}), {"pair": pair})


@pytest.mark.parametrize("day,utc_hour", [("2026-06-01", 13), ("2026-11-02", 14)])
def test_dst_and_first_candidate(day, utc_hour):
    df = session(day)
    out = run(df)
    assert df.loc[24, "date"].hour == utc_hour
    assert out.index[out.enter_long.eq(1)].tolist() == [27]
    assert not out.loc[24, "orb_complete"] and out.loc[26, "orb_complete"]
    assert out.loc[27, "fw_stop"] == pytest.approx(98.901)


def test_range_not_backfilled_and_prefix_stable():
    df = session()
    full = run(df)
    for n in [10, 24, 25, 26, 27, 28, 35, 120]:
        assert_frame_equal(run(df.iloc[:n]), full.iloc[:n])
    assert pd.isna(full.loc[23, "orb_high"])
    df.loc[40:, ["high", "low", "close"]] = [200, 50, 150]
    assert_frame_equal(run(df).iloc[:40], full.iloc[:40])


@pytest.mark.parametrize("missing", [24, 25, 26])
def test_incomplete_opening_range_fails_closed(missing):
    assert run(session().drop(index=missing)).enter_long.sum() == 0


def test_duplicate_opening_bar_invalidates_session():
    df = session()
    df = pd.concat([df.iloc[:26], df.iloc[[25]], df.iloc[26:]], ignore_index=True)
    assert run(df).enter_long.sum() == 0


def test_range_volume_missing_or_low_breakout_volume():
    df = session()
    df.loc[25, "volume"] = 0
    assert run(df).enter_long.sum() == 0
    df.loc[25, "volume"] = float("nan")
    assert run(df).enter_long.sum() == 0
    df = session()
    df.loc[25, "high"] = float("nan")
    assert run(df).enter_long.sum() == 0
    df = session()
    df.loc[[27, 35], "volume"] = 0
    assert run(df).enter_long.sum() == 0


def test_weekend_and_exact_pair_filter():
    assert run(session("2026-06-06")).enter_long.sum() == 0
    assert run(session(), "BTC/USDT").enter_long.sum() == 0
    assert run(session(), "ETH/USDC:USDC").enter_long.sum() == 0


def test_session_resets_and_late_day_is_not_new_window():
    df = pd.concat([session(), session("2026-06-02")], ignore_index=True)
    out = run(df)
    assert out.index[out.enter_long.eq(1)].tolist() == [27, 147]
    late = session()
    late.loc[[27, 35], "volume"] = 0
    extra = late.iloc[[-1]].copy()
    extra.loc[:, "date"] = pd.Timestamp("2026-06-02 03:55Z")  # 23:55 NY, close crosses midnight
    extra.loc[:, ["high", "close", "volume"]] = [104, 103, 100]
    assert run(pd.concat([late, extra], ignore_index=True)).enter_long.sum() == 0


def test_bound_stop_target_and_session_exit():
    now = datetime(2026, 6, 1, 15, tzinfo=timezone.utc)
    t = SimpleNamespace(open_rate=100, open_date_utc=now, get_custom_data=lambda k: 98)
    s = S.__new__(S)
    assert s.strategy_exit("BTC", t, now, 103.9, None) is None
    assert s.strategy_exit("BTC", t, now, 104, None) == "andrea_orb_2R"
    assert s.strategy_exit("BTC", t, pd.Timestamp("2026-06-01 20:00Z"), 100, None) == "andrea_orb_session_end"
    assert s.strategy_exit("BTC", t, pd.Timestamp("2026-06-02 12:00Z"), 100, None) == "andrea_orb_session_end"


def test_framework_controls_inherited():
    for name in ["advise_entry", "custom_stake_amount", "leverage", "custom_stoploss", "custom_exit",
                 "confirm_trade_entry", "order_filled", "informative_pairs", "adjust_trade_position"]:
        assert getattr(S, name) is getattr(FrameworkStrategy, name)
    assert S.framework_params == {}
    assert set(S.research_stress) == {"cost2x", "delay1", "stopslip"}
