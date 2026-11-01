"""OHLCV balanced-range reclaim proxy. No L2, options, gamma or participant inference."""
from __future__ import annotations

import math
import os
import sys
import numpy as np
import pandas as pd
from pandas import DataFrame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy, target_reached, decode_plan  # noqa: E402


class ImreGamsAuctionProxy(FrameworkStrategy):
    timeframe = "1h"
    startup_candle_count = 100
    can_short = True
    framework_params = {}
    balance_hours = 24
    max_width = 0.04
    max_efficiency = 0.25
    lower_zone = 0.35
    volume_multiple = 1.2
    minimum_rr = 1.5
    stop_buffer = 0.001
    max_hours = 24

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        n = self.balance_hours
        df["range_top"] = df["high"].shift(1).rolling(n).max()
        df["range_bottom"] = df["low"].shift(1).rolling(n).min()
        df["range_mid"] = (df["range_top"] + df["range_bottom"]) / 2
        df["range_width"] = (df["range_top"] - df["range_bottom"]) / df["range_mid"]
        path = df["close"].diff().abs().shift(1).rolling(n).sum()
        displacement = (df["close"].shift(1) - df["close"].shift(n + 1)).abs()
        df["efficiency"] = (displacement / path.replace(0, np.nan)).where(path != 0, 0)
        df["prior_volume"] = df["volume"].shift(1).rolling(20).mean()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_short"] = 0
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = np.nan, np.nan
        if not self.pair_enabled(metadata.get("pair")):
            return df
        stop = df["low"] * (1 - self.stop_buffer)
        room = df["range_mid"] - df["close"]
        risk = df["close"] - stop
        cond = ((df["range_width"] > 0) & (df["range_width"] <= self.max_width)
                & (df["efficiency"] <= self.max_efficiency)
                & (df["low"] < df["range_bottom"]) & (df["close"] > df["range_bottom"])
                & (df["close"] < df["range_mid"])
                & (df["close"] <= df["range_bottom"] + self.lower_zone * (df["range_top"] - df["range_bottom"]))
                & (df["close"] > df["open"]) & (df["volume"] > 0)
                & (df["volume"] > df["prior_volume"] * self.volume_multiple)
                & (risk > 0) & (room >= self.minimum_rr * risk))
        df.loc[cond, "enter_long"] = 1
        df.loc[cond, "enter_tag"] = df.loc[cond, "range_mid"].map(lambda x: f"imre_mid:{x:.10g}")
        df.loc[cond, "fw_stop"] = stop[cond]
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * 1.001
        short_stop = df["high"] * (1 + self.stop_buffer)
        short_risk = short_stop - df["close"]
        short_room = df["close"] - df["range_mid"]
        short = ((df["range_width"] > 0) & (df["range_width"] <= self.max_width)
                 & (df["efficiency"] <= self.max_efficiency)
                 & (df["high"] > df["range_top"]) & (df["close"] < df["range_top"])
                 & (df["close"] > df["range_mid"])
                 & (df["close"] >= df["range_top"] - self.lower_zone * (df["range_top"] - df["range_bottom"]))
                 & (df["close"] < df["open"]) & (df["volume"] > 0)
                 & (df["volume"] > df["prior_volume"] * self.volume_multiple)
                 & (short_risk > 0) & (short_room >= self.minimum_rr * short_risk))
        df.loc[short, "enter_short"] = 1
        df.loc[short, "enter_tag"] = df.loc[short, "range_mid"].map(lambda x: f"imre_mid:{x:.10g}")
        df.loc[short, "fw_stop"] = short_stop[short]
        df.loc[short, "fw_entry_cap"] = df.loc[short, "close"] * 0.999
        return self.filter_entry_signals(df, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        plan = decode_plan(trade.enter_tag)
        if plan is not None and plan.get("user", "").startswith("imre_mid:"):
            try:
                target = float(plan["user"].split(":", 1)[1])
            except (ValueError, IndexError):
                target = float("nan")
            if math.isfinite(target) and ((-1 if getattr(trade, "is_short", False) else 1) * (target - trade.open_rate) > 0) and ((-1 if getattr(trade, "is_short", False) else 1) * (current_rate - target) >= 0):
                return "imre_frozen_midpoint"
        if current_time - trade.open_date_utc >= pd.Timedelta(hours=self.max_hours):
            return "imre_example_time_limit"
        return None
