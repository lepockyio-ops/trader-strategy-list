"""Crypto trend/partial-exit proxy, not CAN SLIM, TQQQ or a fundamental growth system."""
from __future__ import annotations

import os
import sys

from pandas import DataFrame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy  # noqa: E402


class VibhaJhaTrend(FrameworkStrategy):
    timeframe = "1d"
    startup_candle_count = 220
    framework_params = {}
    breakout_period = 60
    stop_period = 3
    exit_period = 20

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        for n in (50, 200):
            df[f"sma{n}"] = df["close"].rolling(n).mean()
        df["exit_sma"] = df["close"].rolling(self.exit_period).mean()
        df["breakout"] = df["high"].shift(1).rolling(self.breakout_period).max()
        df["stop_low"] = df["low"].rolling(self.stop_period).min()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = float("nan"), float("nan")
        if metadata.get("pair") not in {"BTC/USDT:USDT", "ETH/USDT:USDT"}:
            return df
        trend = ((df["sma50"] > df["sma200"]) & (df["sma50"] > df["sma50"].shift(5))
                 & (df["close"] > df["sma50"]))
        cross = (df["close"] > df["breakout"]) & (df["close"].shift(1) <= df["breakout"].shift(1))
        cond = trend & cross & (df["volume"] > 0) & (df["close"] > df["open"])
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "vibha_trend_proxy_v1")
        df.loc[cond, "fw_stop"] = df.loc[cond, "stop_low"] * 0.999
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * 1.001
        return df

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def take_profit_legs(self, trade):
        return [(2.0, 0.5, "vibha_2R_half")]

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        if last_row is not None and last_row.get("close", float("nan")) < last_row.get("exit_sma", float("nan")):
            return "vibha_trend_lost"
        return None
