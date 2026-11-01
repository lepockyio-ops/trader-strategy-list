"""OHLCV AVWAP confirmation proxy. All parameters are unvalidated examples."""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import informative

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy, target_reached  # noqa: E402


def confirmed_low_avwap(dataframe: DataFrame, radius: int = 2, high_anchor: bool = False) -> DataFrame:
    """Only expose a candidate's AVWAP after its right-hand confirmation bars close."""
    df = dataframe.copy()
    low = df["high"] if high_anchor else df["low"]
    candidate = low.shift(radius)
    pivot = (((candidate > low.shift(radius + 1).rolling(radius).max())
              & (candidate > low.rolling(radius).max())) if high_anchor else
             ((candidate < low.shift(radius + 1).rolling(radius).min())
              & (candidate < low.rolling(radius).min())))
    price = (df["high"] + df["low"] + df["close"]) / 3
    volume = df["volume"].clip(lower=0).fillna(0)
    pv = (price * volume).cumsum().to_numpy()
    vv = volume.cumsum().to_numpy()
    averages, anchors = np.full(len(df), np.nan), np.full(len(df), np.nan)
    anchor = None
    for i in range(len(df)):
        if bool(pivot.iloc[i]):
            anchor = i - radius
        if anchor is not None:
            base_pv = pv[anchor - 1] if anchor else 0
            base_v = vv[anchor - 1] if anchor else 0
            denom = vv[i] - base_v
            averages[i] = (pv[i] - base_pv) / denom if denom > 0 else np.nan
            # Timestamp, not a row count, remains stable when prior data is truncated.
            anchors[i] = pd.Timestamp(df["date"].iloc[anchor]).value / 1e9
    df["avwap"], df["avwap_anchor"] = averages, anchors
    return df


class BrianShannonAVWAP(FrameworkStrategy):
    timeframe = "1h"
    startup_candle_count = 240
    can_short = True
    framework_params = {}
    pivot_radius = 2
    recovery_hours = 3
    stop_hours = 6
    stop_buffer = 0.001
    entry_cap_buffer = 0.001

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["sma50"] = df["close"].rolling(50).mean()
        df["trend_ok"] = ((df["close"] > df["sma50"])
                          & (df["sma50"] >= df["sma50"].shift(5))).astype(int)
        df["trend_short"] = ((df["close"] < df["sma50"]) & (df["sma50"] <= df["sma50"].shift(5))).astype(int)
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = confirmed_low_avwap(dataframe, self.pivot_radius)
        df["recovery_high"] = df["high"].shift(1).rolling(self.recovery_hours).max()
        df["related_low"] = df["low"].rolling(self.stop_hours).min()
        df["prior_low"] = df["low"].shift(1).rolling(self.stop_hours).min()
        high = confirmed_low_avwap(dataframe, self.pivot_radius, high_anchor=True)
        df["high_avwap"], df["high_avwap_anchor"] = high["avwap"], high["avwap_anchor"]
        df["recovery_low"] = df["low"].shift(1).rolling(self.recovery_hours).min()
        df["related_high"] = df["high"].rolling(self.stop_hours).max()
        df["prior_high"] = df["high"].shift(1).rolling(self.stop_hours).max()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_short"] = 0
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = np.nan, np.nan
        if not self.pair_enabled(metadata.get("pair")) or "trend_ok_1d" not in df:
            return df
        same_anchor = df["avwap_anchor"].eq(df["avwap_anchor"].shift(1))
        cond = (same_anchor & df["trend_ok_1d"].eq(1)
                & (df["close"].shift(1) <= df["avwap"].shift(1))
                & (df["close"] > df["avwap"])
                & (df["avwap"] >= df["avwap"].shift(1))
                & (df["close"] > df["recovery_high"])
                & (df["close"] > df["open"]) & (df["volume"] > 0))
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "shannon_avwap_proxy_v1")
        df.loc[cond, "fw_stop"] = df.loc[cond, "related_low"] * (1 - self.stop_buffer)
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * (1 + self.entry_cap_buffer)
        if "trend_short_1d" in df:
            same_high = df["high_avwap_anchor"].eq(df["high_avwap_anchor"].shift(1))
            short = (same_high & df["trend_short_1d"].eq(1)
                     & (df["close"].shift(1) >= df["high_avwap"].shift(1))
                     & (df["close"] < df["high_avwap"])
                     & (df["high_avwap"] <= df["high_avwap"].shift(1))
                     & (df["close"] < df["recovery_low"]) & (df["close"] < df["open"])
                     & (df["volume"] > 0))
            df.loc[short, ["enter_short", "enter_tag"]] = (1, "shannon_short_proxy_v2")
            df.loc[short, "fw_stop"] = df.loc[short, "related_high"] * (1 + self.stop_buffer)
            df.loc[short, "fw_entry_cap"] = df.loc[short, "close"] * (1 - self.entry_cap_buffer)
        return self.filter_entry_signals(df, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def take_profit_legs(self, trade):
        return [(1.0, 1 / 3, "shannon_first_third")]

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        if getattr(trade, "is_short", False):
            if last_row is not None and (last_row.get("close", np.nan) > last_row.get("high_avwap", np.nan)
                                         and last_row.get("close", np.nan) > last_row.get("prior_high", np.nan)):
                return "shannon_structure_failed"
            return None
        if last_row is not None and (last_row.get("close", np.nan) < last_row.get("avwap", np.nan)
                                     and last_row.get("close", np.nan) < last_row.get("prior_low", np.nan)):
            return "shannon_structure_failed"
        return None
