"""Daily rectangle proxy; not Brandt's full chart-reading process. Example thresholds."""
from __future__ import annotations

import math
import os
import sys
import numpy as np
import pandas as pd
from pandas import DataFrame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy  # noqa: E402


class PeterBrandtRectangle(FrameworkStrategy):
    timeframe = "1d"
    startup_candle_count = 100
    framework_params = {}
    rectangle_days = 42
    max_width = 0.15
    touch_tolerance = 0.005
    min_touches = 2
    breakout_buffer = 0.001
    stop_buffer = 0.001
    target_r = 3.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        hi = df["high"].shift(1).rolling(self.rectangle_days)
        lo = df["low"].shift(1).rolling(self.rectangle_days)
        df["box_top"], df["box_bottom"] = hi.max(), lo.min()
        df["box_width"] = (df["box_top"] - df["box_bottom"]) / df["box_bottom"]
        df["top_touches"] = hi.apply(lambda x: np.sum(x >= x.max() * (1 - self.touch_tolerance)), raw=True)
        df["bottom_touches"] = lo.apply(lambda x: np.sum(x <= x.min() * (1 + self.touch_tolerance)), raw=True)
        df["prior_close"] = df["close"].shift(1)
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = np.nan, np.nan
        if metadata.get("pair") not in {"BTC/USDT:USDT", "ETH/USDT:USDT"}:
            return df
        level = df["box_top"] * (1 + self.breakout_buffer)
        cond = ((df["box_width"] > 0) & (df["box_width"] <= self.max_width)
                & (df["top_touches"] >= self.min_touches) & (df["bottom_touches"] >= self.min_touches)
                & (df["close"] > level) & (df["close"].shift(1) <= level.shift(1))
                & (df["close"] > df["open"]) & (df["volume"] > 0))
        df.loc[cond, ["enter_long", "enter_tag"]] = (1, "brandt_rectangle_proxy_v1")
        df.loc[cond, "fw_stop"] = df.loc[cond, "box_bottom"] * (1 - self.stop_buffer)
        df.loc[cond, "fw_entry_cap"] = df.loc[cond, "close"] * 1.001
        return df

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        stop = trade.get_custom_data("stop_px")
        if stop is not None and math.isfinite(float(stop)) and trade.open_rate > float(stop):
            if current_rate >= trade.open_rate + self.target_r * (trade.open_rate - float(stop)):
                return "brandt_example_3R"
        if last_row is None or pd.isna(last_row.get("date")):
            return None
        day = pd.Timestamp(last_row["date"])
        opened = pd.Timestamp(trade.open_date_utc)
        # Count only complete daily candles that began after the actual fill.
        if day - pd.Timedelta(days=1) >= opened and last_row.get("close", np.nan) < trade.open_rate:
            if last_row.get("prior_close", np.nan) < trade.open_rate:
                return "brandt_two_losing_days"
        if day >= opened and day.dayofweek == 4 and last_row.get("close", np.nan) < trade.open_rate:
            return "brandt_losing_utc_friday"
        return None
