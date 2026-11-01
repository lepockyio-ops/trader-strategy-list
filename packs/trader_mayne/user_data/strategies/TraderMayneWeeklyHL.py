"""Mayne-inspired research proxy, not his disclosed system. Spec: docs/TRADER_MAYNE_STRATEGY.md.

All strategy numbers below are unvalidated examples. Execution and risk callbacks belong
to FrameworkStrategy. No future pivots, final-week lows, or discretionary trade overrides.
"""
from __future__ import annotations

import math
import os
import sys

import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import informative

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy  # noqa: E402


def confirmed_structure(dataframe: DataFrame, radius: int = 2) -> DataFrame:
    """Record each strict pivot at its confirmation time, never at the historical pivot."""
    df = dataframe.copy()
    for field, high in (("high", True), ("low", False)):
        series = df[field]
        candidate = series.shift(radius)
        left = series.shift(radius + 1).rolling(radius)
        right = series.rolling(radius)
        valid = ((candidate > left.max()) & (candidate > right.max()) if high else
                 (candidate < left.min()) & (candidate < right.min()))
        event = candidate.where(valid)
        df[f"pivot_{field}"] = event
        df[f"last_{field}"] = event.ffill()
        df[f"previous_{field}"] = event.ffill().shift(1).where(valid).ffill()
    df["bull_structure"] = (
        (df["last_high"] > df["previous_high"])
        & (df["last_low"] > df["previous_low"])
        & (df["close"] > df["last_low"])
    ).astype(int)
    return df


class TraderMayneWeeklyHL(FrameworkStrategy):
    timeframe = "1h"
    startup_candle_count = 240
    framework_params = {}  # Deliberately inherit all framework risk/venue settings.
    pivot_radius = 2
    recovery_hours = 6
    stop_buffer = 0.001
    entry_cap_buffer = 0.001
    target_r = 2.0

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return confirmed_structure(dataframe, self.pivot_radius)

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        dates = pd.to_datetime(df["date"], utc=True)
        day = dates.dt.normalize()
        week = day - pd.to_timedelta(dates.dt.dayofweek, unit="D")
        df["mayne_week"] = week
        df["week_low"] = df["low"].groupby(week).cummin()
        df["week_open"] = df["open"].groupby(week).transform("first")
        df["full_week_start"] = dates.groupby(week).transform("first").eq(week)
        close_dates = dates + pd.Timedelta(hours=1)
        df["early_week"] = (dates.dt.dayofweek <= 2) & (close_dates.dt.dayofweek <= 2)
        df["recovery_high"] = df["high"].shift(1).rolling(self.recovery_hours).max()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_long"] = 0
        df["enter_tag"] = ""
        df["fw_stop"] = float("nan")
        df["fw_entry_cap"] = float("nan")
        if metadata.get("pair") not in {"BTC/USDT:USDT", "ETH/USDT:USDT"}:
            return df
        if not {"bull_structure_1d", "last_low_1d"}.issubset(df.columns):
            return df  # Missing higher-timeframe data must not turn into permission.
        cross = ((df["close"] > df["recovery_high"])
                 & (df["close"].shift(1) <= df["recovery_high"].shift(1)))
        candidate = (
            df["full_week_start"] & df["early_week"]
            & df["bull_structure_1d"].eq(1)
            & (df["week_low"] > df["last_low_1d"])
            & (df["week_low"] < df["week_open"])
            & cross & (df["close"] > df["open"]) & (df["volume"] > 0)
        ).fillna(False)
        # First eligible candidate, not first fill: deterministic even if a guard rejects it.
        first = candidate & candidate.groupby(df["mayne_week"]).cumsum().eq(1)
        df.loc[first, "enter_long"] = 1
        df.loc[first, "enter_tag"] = "mayne_weekly_hl_v1"
        df.loc[first, "fw_stop"] = df.loc[first, "week_low"] * (1 - self.stop_buffer)
        df.loc[first, "fw_entry_cap"] = df.loc[first, "close"] * (1 + self.entry_cap_buffer)
        return df

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        # The parent binds and validates this stop before calling the hook.
        stop = trade.get_custom_data("stop_px")
        if stop is None or not math.isfinite(float(stop)) or trade.open_rate <= float(stop):
            return None
        target = trade.open_rate + self.target_r * (trade.open_rate - float(stop))
        return "mayne_2R" if current_rate >= target else None
