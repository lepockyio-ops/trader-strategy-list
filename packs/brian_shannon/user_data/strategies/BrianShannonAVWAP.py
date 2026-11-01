"""OHLCV AVWAP confirmation proxy. All parameters are unvalidated examples."""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd
from pandas import DataFrame
from freqtrade.strategy import informative

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy  # noqa: E402


def confirmed_low_avwap(dataframe: DataFrame, radius: int = 2) -> DataFrame:
    """Only expose a candidate's AVWAP after its right-hand confirmation bars close."""
    df = dataframe.copy()
    low = df["low"]
    candidate = low.shift(radius)
    pivot = ((candidate < low.shift(radius + 1).rolling(radius).min())
             & (candidate < low.rolling(radius).min()))
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
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = confirmed_low_avwap(dataframe, self.pivot_radius)
        df["recovery_high"] = df["high"].shift(1).rolling(self.recovery_hours).max()
        df["related_low"] = df["low"].rolling(self.stop_hours).min()
        df["prior_low"] = df["low"].shift(1).rolling(self.stop_hours).min()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = np.nan, np.nan
        if metadata.get("pair") not in {"BTC/USDT:USDT", "ETH/USDT:USDT"} or "trend_ok_1d" not in df:
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
        return df

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def take_profit_legs(self, trade):
        return [(1.0, 1 / 3, "shannon_first_third")]

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        if last_row is not None and (last_row.get("close", np.nan) < last_row.get("avwap", np.nan)
                                     and last_row.get("close", np.nan) < last_row.get("prior_low", np.nan)):
            return "shannon_structure_failed"
        return None
