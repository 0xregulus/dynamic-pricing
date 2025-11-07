"""
Signal generation utilities for crypto price series.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_volatility(series: pd.Series, window: int) -> pd.Series:
    """Rolling annualized volatility (approx)."""

    ratio = series / series.shift(1)
    ratio = ratio.replace(0, np.nan)
    log_returns = np.log(ratio)
    log_returns = log_returns.replace([np.inf, -np.inf], np.nan).fillna(0)
    return log_returns.rolling(window).std(ddof=0) * (window ** 0.5)


def compute_momentum(series: pd.Series, window: int) -> pd.Series:
    return series.pct_change(periods=window)


def compute_trend_strength(series: pd.Series, short: int, long: int) -> pd.Series:
    short_ma = series.rolling(short).mean()
    long_ma = series.rolling(long).mean()
    long_ma = long_ma.replace(0, np.nan)
    return (short_ma - long_ma) / long_ma


def build_feature_frame(prices: pd.DataFrame, smoothing_window: int) -> pd.DataFrame:
    frame = prices.copy()
    frame["sma"] = frame["price"].rolling(smoothing_window).mean()
    frame["momentum"] = compute_momentum(frame["price"], smoothing_window)
    frame["volatility"] = compute_volatility(frame["price"], smoothing_window)
    short_window = max(2, smoothing_window // 2)
    frame["trend_strength"] = compute_trend_strength(frame["price"], short_window, smoothing_window)
    return frame.dropna().reset_index(drop=True)


__all__ = [
    "build_feature_frame",
    "compute_momentum",
    "compute_trend_strength",
    "compute_volatility",
]
