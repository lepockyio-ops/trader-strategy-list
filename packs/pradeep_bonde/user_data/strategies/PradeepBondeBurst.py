"""Unvalidated OHLCV momentum burst; no catalyst, theme or premarket information input."""
from __future__ import annotations

import os
import sys

from pandas import DataFrame
from freqtrade.strategy import informative

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy, target_reached  # noqa: E402


class PradeepBondeBurst(FrameworkStrategy):
    timeframe = "1h"
    startup_candle_count = 100
    can_short = True
    framework_params = {}
    burst_return = 0.04
    breakout_period = 20
    volume_multiple = 1.5

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["sma50"] = df["close"].rolling(50).mean()
        df["trend_ok"] = (df["close"] > df["sma50"]).astype(int)
        df["trend_short"] = (df["close"] < df["sma50"]).astype(int)
        return df

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["exit_sma"] = df["close"].rolling(10).mean()
        df["return24"] = df["close"] / df["close"].shift(24) - 1
        df["breakout"] = df["high"].shift(1).rolling(self.breakout_period).max()
        df["volume_mean"] = df["volume"].shift(1).rolling(20).mean()
        df["stop_low"] = df["low"].rolling(3).min()
        df["breakdown"] = df["low"].shift(1).rolling(self.breakout_period).min()
        df["stop_high"] = df["high"].rolling(3).max()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_short"] = 0
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = float("nan"), float("nan")
        if not self.pair_enabled(metadata.get("pair")) or "trend_ok_1d" not in df:
            return df
        cross = (df["close"] > df["breakout"]) & (df["close"].shift(1) <= df["breakout"].shift(1))
        cond = (cross & (df["return24"] >= self.burst_return)
                & (df["volume"] >= df["volume_mean"] * self.volume_multiple)
                & df["trend_ok_1d"].eq(1) & (df["close"] > df["open"])
                & (df["volume"] > 0))
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "bonde_burst_proxy_v1")
        df.loc[cond, "fw_stop"] = df.loc[cond, "stop_low"] * 0.999
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * 1.001
        if "trend_short_1d" in df:
            breakdown = ((df["close"] < df["breakdown"])
                         & (df["close"].shift(1) >= df["breakdown"].shift(1)))
            short = (breakdown & (df["return24"] <= -self.burst_return)
                     & (df["volume"] >= df["volume_mean"] * self.volume_multiple)
                     & df["trend_short_1d"].eq(1) & (df["close"] < df["open"]) & (df["volume"] > 0))
            df.loc[short, ["enter_short", "enter_tag"]] = (1, "bonde_short_proxy_v2")
            df.loc[short, "fw_stop"] = df.loc[short, "stop_high"] * 1.001
            df.loc[short, "fw_entry_cap"] = df.loc[short, "close"] * 0.999
        return self.filter_entry_signals(df, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def take_profit_legs(self, trade):
        return [(2.0, 0.8, "bonde_2R_eighty")]

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        if last_row is not None and ((-1 if getattr(trade, "is_short", False) else 1) * (last_row.get("close", float("nan")) - last_row.get("exit_sma", float("nan"))) < 0):
            return "bonde_momentum_lost"
        return None
