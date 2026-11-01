"""Two-stage failed-auction price proxy, not footprint/Delta order-flow inference."""
from __future__ import annotations

import os
import sys
from datetime import timedelta

import numpy as np
from pandas import DataFrame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy, target_reached, decode_plan  # noqa: E402


class ChrisCreamerFailedAuctionProxy(FrameworkStrategy):
    timeframe = "5m"
    startup_candle_count = 40
    can_short = True
    framework_params = {}
    box_bars = 24
    max_box_width = 0.03
    failure_volume_multiple = 1.5
    min_reward_r = 1.5
    stop_buffer = 0.001
    cap_buffer = 0.001

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["box_low"] = df.low.shift(2).rolling(self.box_bars).min()
        df["box_high"] = df.high.shift(2).rolling(self.box_bars).max()
        df["box_volume"] = df.volume.shift(2).rolling(self.box_bars).mean()
        df["box_mid"] = (df.box_low + df.box_high) / 2
        df["candidate_stop"] = df.low.rolling(2).min() * (1 - self.stop_buffer)
        df["short_stop"] = df.high.rolling(2).max() * (1 + self.stop_buffer)
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_short"] = 0
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = np.nan, np.nan
        if not self.pair_enabled(metadata.get("pair")):
            return df
        balanced = ((df.box_low > 0) & ((df.box_high - df.box_low) / df.box_low <= self.max_box_width))
        failure = ((df.low.shift(1) < df.box_low) & (df.close.shift(1) < df.box_low)
                   & (df.volume.shift(1) >= self.failure_volume_multiple * df.box_volume))
        recovery = ((df.close > df.box_low) & (df.close > df.high.shift(1)) & (df.close > df.open)
                    & (df.box_volume > 0) & (df.volume >= df.box_volume))
        space = ((df.close > df.candidate_stop)
                 & (df.box_mid - df.close >= self.min_reward_r * (df.close - df.candidate_stop)))
        cond = balanced & failure & recovery & space
        df.loc[cond, "enter_long"] = 1
        df.loc[cond, "enter_tag"] = df.loc[cond, "box_mid"].map(lambda v: f"cc_mid:{v:.10g}")
        df.loc[cond, "fw_stop"] = df.loc[cond, "candidate_stop"]
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * (1 + self.cap_buffer)
        failed_high = ((df.high.shift(1) > df.box_high) & (df.close.shift(1) > df.box_high)
                       & (df.volume.shift(1) >= self.failure_volume_multiple * df.box_volume))
        rejection = ((df.close < df.box_high) & (df.close < df.low.shift(1)) & (df.close < df.open)
                     & (df.box_volume > 0) & (df.volume >= df.box_volume))
        short_space = ((df.short_stop > df.close)
                       & (df.close - df.box_mid >= self.min_reward_r * (df.short_stop - df.close)))
        short = balanced & failed_high & rejection & short_space
        df.loc[short, "enter_short"] = 1
        df.loc[short, "enter_tag"] = df.loc[short, "box_mid"].map(lambda v: f"cc_mid:{v:.10g}")
        df.loc[short, "fw_stop"] = df.loc[short, "short_stop"]
        df.loc[short, "fw_entry_cap"] = df.loc[short, "close"] * (1 - self.cap_buffer)
        return self.filter_entry_signals(df, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        plan = decode_plan(trade.enter_tag)
        user = plan.get("user", "") if plan else ""
        if user.startswith("cc_mid:"):
            try:
                target = float(user.split(":", 1)[1])
            except ValueError:
                target = np.nan
            if np.isfinite(target) and ((-1 if getattr(trade, "is_short", False) else 1) * (target - trade.open_rate) > 0) and ((-1 if getattr(trade, "is_short", False) else 1) * (current_rate - target) >= 0):
                return "creamer_proxy_mid"
        if current_time - trade.open_date_utc >= timedelta(minutes=60):
            return "creamer_proxy_time"
        return None
