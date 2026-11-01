"""Unvalidated trend-pullback proxy; see the pack's STRATEGY.md, not an original Luk system."""
from __future__ import annotations

import math
import os
import sys

from pandas import DataFrame
from freqtrade.strategy import informative

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy  # noqa: E402


class MartinLukPullback(FrameworkStrategy):
    timeframe = "1h"
    startup_candle_count = 240
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
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["support"] = df["close"].rolling(self.support_period).mean()
        df["stop_low"] = df["low"].rolling(self.stop_period).min()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = float("nan"), float("nan")
        if metadata.get("pair") not in {"BTC/USDT:USDT", "ETH/USDT:USDT"} or "trend_ok_1d" not in df:
            return df
        pullback = ((df["low"].shift(1) <= df["support"].shift(1))
                    & (df["close"].shift(1) <= df["support"].shift(1) * 1.005))
        cond = (df["trend_ok_1d"].eq(1) & pullback & (df["close"] > df["support"])
                & (df["close"] > df["high"].shift(1)) & (df["close"] > df["open"])
                & (df["volume"] > 0) & df["stop_low"].notna())
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "luk_pullback_proxy_v1")
        df.loc[cond, "fw_stop"] = df.loc[cond, "stop_low"] * 0.999
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * 1.001
        return df

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        stop = trade.get_custom_data("stop_px")
        if stop is None or not math.isfinite(float(stop)) or trade.open_rate <= float(stop):
            return None
        return "luk_3R" if current_rate >= trade.open_rate + self.target_r * (trade.open_rate - float(stop)) else None
