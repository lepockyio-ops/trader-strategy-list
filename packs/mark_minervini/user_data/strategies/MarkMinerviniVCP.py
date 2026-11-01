"""Causal three-block contraction proxy; omits SEPA fundamentals and cross-stock RS."""
from __future__ import annotations

import math
import os
import sys

from pandas import DataFrame
from freqtrade.strategy import informative

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy  # noqa: E402


class MarkMinerviniVCP(FrameworkStrategy):
    timeframe = "4h"
    startup_candle_count = 260
    framework_params = {}
    block = 5
    volume_multiple = 1.2
    target_r = 3.0

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        for n in (50, 150, 200):
            df[f"sma{n}"] = df["close"].rolling(n).mean()
        df["trend_ok"] = ((df["close"] > df["sma50"]) & (df["sma50"] > df["sma150"])
                          & (df["sma150"] > df["sma200"])
                          & (df["sma200"] > df["sma200"].shift(20))).astype(int)
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        n = self.block
        for k in range(3):
            shift = 1 + k * n
            df[f"range{k}"] = (df["high"].shift(shift).rolling(n).max()
                                - df["low"].shift(shift).rolling(n).min())
            df[f"volume{k}"] = df["volume"].shift(shift).rolling(n).mean()
        df["breakout"] = df["high"].shift(1).rolling(3 * n).max()
        df["stop_low"] = df["low"].shift(1).rolling(n).min()
        df["volume_mean"] = df["volume"].shift(1).rolling(20).mean()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = float("nan"), float("nan")
        if metadata.get("pair") not in {"BTC/USDT:USDT", "ETH/USDT:USDT"} or "trend_ok_1d" not in df:
            return df
        contraction = ((df["range2"] > df["range1"]) & (df["range1"] > df["range0"])
                       & (df["range0"] > 0) & (df["volume0"] < df["volume2"]))
        cross = (df["close"] > df["breakout"]) & (df["close"].shift(1) <= df["breakout"].shift(1))
        cond = (df["trend_ok_1d"].eq(1) & contraction & cross & (df["volume"] > 0)
                & (df["volume"] > df["volume_mean"] * self.volume_multiple))
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "minervini_vcp_proxy_v1")
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
        return "minervini_3R" if current_rate >= trade.open_rate + self.target_r * (trade.open_rate - float(stop)) else None
