"""Unvalidated trend-pullback proxy; see the pack's STRATEGY.md, not an original Luk system."""
from __future__ import annotations

import math
import os
import sys

from pandas import DataFrame
from freqtrade.strategy import informative

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy, target_reached  # noqa: E402


class MartinLukPullback(FrameworkStrategy):
    timeframe = "1h"
    startup_candle_count = 240
    can_short = True
    framework_params = {}
    support_period = 20
    stop_period = 4
    target_r = 3.0

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["sma50"] = df["close"].rolling(50).mean()
        df["trend_ok"] = ((df["close"] > df["sma50"])
                          & (df["sma50"] > df["sma50"].shift(5))).astype(int)
        df["trend_short"] = ((df["close"] < df["sma50"]) & (df["sma50"] < df["sma50"].shift(5))).astype(int)
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["support"] = df["close"].rolling(self.support_period).mean()
        df["stop_low"] = df["low"].rolling(self.stop_period).min()
        df["stop_high"] = df["high"].rolling(self.stop_period).max()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_short"] = 0
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = float("nan"), float("nan")
        if not self.pair_enabled(metadata.get("pair")) or "trend_ok_1d" not in df:
            return df
        pullback = ((df["low"].shift(1) <= df["support"].shift(1))
                    & (df["close"].shift(1) <= df["support"].shift(1) * 1.005))
        cond = (df["trend_ok_1d"].eq(1) & pullback & (df["close"] > df["support"])
                & (df["close"] > df["high"].shift(1)) & (df["close"] > df["open"])
                & (df["volume"] > 0) & df["stop_low"].notna())
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "luk_pullback_proxy_v1")
        df.loc[cond, "fw_stop"] = df.loc[cond, "stop_low"] * 0.999
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * 1.001
        if "trend_short_1d" in df:
            bounce = ((df["high"].shift(1) >= df["support"].shift(1))
                      & (df["close"].shift(1) >= df["support"].shift(1) * 0.995))
            short = (df["trend_short_1d"].eq(1) & bounce & (df["close"] < df["support"])
                     & (df["close"] < df["low"].shift(1)) & (df["close"] < df["open"])
                     & (df["volume"] > 0) & df["stop_high"].notna())
            df.loc[short, ["enter_short", "enter_tag"]] = (1, "luk_short_proxy_v2")
            df.loc[short, "fw_stop"] = df.loc[short, "stop_high"] * 1.001
            df.loc[short, "fw_entry_cap"] = df.loc[short, "close"] * 0.999
        return self.filter_entry_signals(df, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        return "luk_3R" if target_reached(trade, current_rate, self.target_r) else None
