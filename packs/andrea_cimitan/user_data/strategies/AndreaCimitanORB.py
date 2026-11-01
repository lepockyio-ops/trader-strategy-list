"""NY-clock crypto ORB proxy; no L2, trade bubbles, options or exchange holiday calendar."""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd
from pandas import DataFrame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from framework_base import FrameworkStrategy, target_reached  # noqa: E402


class AndreaCimitanORB(FrameworkStrategy):
    timeframe = "5m"
    startup_candle_count = 300
    can_short = True
    framework_params = {}
    volume_multiple = 1.2
    stop_buffer = 0.001
    cap_buffer = 0.001
    target_r = 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        ny = pd.to_datetime(df.date, utc=True).dt.tz_convert("America/New_York")
        session = ny.dt.strftime("%Y-%m-%d")
        minute = ny.dt.hour * 60 + ny.dt.minute
        opening = minute.isin([570, 575, 580]) & (ny.dt.dayofweek < 5)
        df["ny_session"] = session
        df["orb_high"] = df.high.where(opening).groupby(session).cummax().groupby(session).ffill()
        df["orb_low"] = df.low.where(opening).groupby(session).cummin().groupby(session).ffill()
        count = opening.astype(int).groupby(session).cumsum()
        has_start = minute.eq(570).where(opening, False).groupby(session).cummax()
        missing_bar = df[["open", "high", "low", "close"]].isna().any(axis=1)
        bad_volume = (opening & (~df.volume.gt(0) | missing_bar)).astype(int).groupby(session).cumsum()
        duplicates = pd.MultiIndex.from_arrays([session, minute]).duplicated()
        bad_duplicates = (opening & duplicates).astype(int).groupby(session).cumsum()
        df["orb_complete"] = (count == 3) & has_start & bad_volume.eq(0) & bad_duplicates.eq(0)
        close_ny = ny + pd.Timedelta(minutes=5)
        close_minute = close_ny.dt.hour * 60 + close_ny.dt.minute
        df["orb_window"] = ((minute >= 585) & (minute < 690)
                            & (close_minute <= 690) & (ny.dt.dayofweek < 5))
        df["prior_volume"] = df.volume.shift(1).rolling(20).mean()
        return df

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        df = dataframe.copy()
        df["enter_short"] = 0
        df["enter_long"], df["enter_tag"] = 0, ""
        df["fw_stop"], df["fw_entry_cap"] = np.nan, np.nan
        if not self.pair_enabled(metadata.get("pair")):
            return df
        cross = (df.close > df.orb_high) & (df.close.shift(1) <= df.orb_high)
        candidate = (df.orb_complete & df.orb_window & cross & (df.close > df.open)
                     & (df.prior_volume > 0) & (df.volume >= self.volume_multiple * df.prior_volume))
        first = candidate & candidate.groupby(df.ny_session).cumsum().eq(1)
        df.loc[first, ["enter_long", "enter_tag"]] = [1, "andrea_orb_proxy_v1"]
        df.loc[first, "fw_stop"] = df.loc[first, "orb_low"] * (1 - self.stop_buffer)
        df.loc[first, "fw_entry_cap"] = df.loc[first, "close"] * (1 + self.cap_buffer)
        breakdown = (df.close < df.orb_low) & (df.close.shift(1) >= df.orb_low)
        short_candidate = (df.orb_complete & df.orb_window & breakdown & (df.close < df.open)
                           & (df.prior_volume > 0) & (df.volume >= self.volume_multiple * df.prior_volume))
        first_short = short_candidate & short_candidate.groupby(df.ny_session).cumsum().eq(1)
        df.loc[first_short, ["enter_short", "enter_tag"]] = [1, "andrea_short_proxy_v2"]
        df.loc[first_short, "fw_stop"] = df.loc[first_short, "orb_high"] * (1 + self.stop_buffer)
        df.loc[first_short, "fw_entry_cap"] = df.loc[first_short, "close"] * (1 - self.cap_buffer)
        return self.filter_entry_signals(df, metadata)

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"], dataframe["exit_short"] = 0, 0
        return dataframe

    def strategy_exit(self, pair, trade, current_time, current_rate, last_row):
        if target_reached(trade, current_rate, self.target_r):
            return "andrea_orb_2R"
        now = pd.Timestamp(current_time).tz_convert("America/New_York")
        opened = pd.Timestamp(trade.open_date_utc).tz_convert("America/New_York")
        if now.date() > opened.date() or now.hour >= 16:
            return "andrea_orb_session_end"
        return None
