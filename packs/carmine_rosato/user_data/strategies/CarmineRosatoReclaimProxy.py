"""Causal OHLCV rejection proxy; does not observe absorption or trader identity."""
from __future__ import annotations

import math
import os
import sys
from datetime import timedelta

import numpy as np
from pandas import DataFrame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy, target_reached  # noqa: E402


class CarmineRosatoReclaimProxy(FrameworkStrategy):
    timeframe = "15m"
    startup_candle_count = 60
    can_short = True
    framework_params = {}
    support_bars = 20
    volume_multiple = 1.5
    wick_fraction = 0.5
    stop_buffer = 0.001
    cap_buffer = 0.001
    target_r = 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["prior_support"] = df.low.shift(1).rolling(self.support_bars).min()
        df["prior_volume"] = df.volume.shift(1).rolling(20).mean()
        span = (df.high - df.low).replace(0, np.nan)
        df["lower_wick_fraction"] = (df[["open", "close"]].min(axis=1) - df.low) / span
        df["sma50"] = df.close.rolling(50).mean()
        df["nonfalling"] = df.sma50 >= df.sma50.shift(5)
        df["prior_resistance"] = df.high.shift(1).rolling(self.support_bars).max()
        df["upper_wick_fraction"] = (df.high - df[["open", "close"]].max(axis=1)) / span
        df["nonrising"] = df.sma50 <= df.sma50.shift(5)
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_short"] = 0
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = np.nan, np.nan
        if not self.pair_enabled(metadata.get("pair")):
            return df
        cond = ((df.low < df.prior_support) & (df.close > df.prior_support)
                & (df.close > df.open) & df.nonfalling
                & (df.lower_wick_fraction >= self.wick_fraction)
                & (df.prior_volume > 0) & (df.volume >= self.volume_multiple * df.prior_volume))
        df.loc[cond, ["enter_long", "enter_tag"]] = [1, "carmine_reclaim_proxy_v1"]
        df.loc[cond, "fw_stop"] = df.loc[cond, "low"] * (1 - self.stop_buffer)
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * (1 + self.cap_buffer)
        short = ((df.high > df.prior_resistance) & (df.close < df.prior_resistance)
                 & (df.close < df.open) & df.nonrising
                 & (df.upper_wick_fraction >= self.wick_fraction)
                 & (df.prior_volume > 0) & (df.volume >= self.volume_multiple * df.prior_volume))
        df.loc[short, ["enter_short", "enter_tag"]] = [1, "carmine_short_proxy_v2"]
        df.loc[short, "fw_stop"] = df.loc[short, "high"] * (1 + self.stop_buffer)
        df.loc[short, "fw_entry_cap"] = df.loc[short, "close"] * (1 - self.cap_buffer)
        return self.filter_entry_signals(df, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        if target_reached(trade, current_rate, self.target_r):
            return "carmine_proxy_2R"
        if current_time - trade.open_date_utc >= timedelta(hours=8):
            return "carmine_proxy_time"
        return None
