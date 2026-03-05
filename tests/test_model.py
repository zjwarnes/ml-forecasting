"""Tests for model predictions and fallback behavior."""

import pandas as pd
import numpy as np
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.fallback import seasonal_naive_forecast


def _make_history(n_days=30, store="test_store"):
    dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
    return pd.DataFrame({
        "unique_id": store,
        "ds": dates,
        "y": np.random.default_rng(42).uniform(50, 200, n_days).round(2),
    })


def test_seasonal_naive_non_negative():
    history = _make_history()
    forecast = seasonal_naive_forecast(history, horizon=7)
    assert (forecast["SeasonalNaive"] >= 0).all()


def test_seasonal_naive_correct_shape():
    history = _make_history()
    forecast = seasonal_naive_forecast(history, horizon=7)
    assert len(forecast) == 7
    assert set(forecast.columns) == {"unique_id", "ds", "SeasonalNaive"}


def test_seasonal_naive_multi_store():
    h1 = _make_history(store="store_1")
    h2 = _make_history(store="store_2")
    history = pd.concat([h1, h2], ignore_index=True)
    forecast = seasonal_naive_forecast(history, horizon=7)
    assert len(forecast) == 14  # 7 per store
    assert set(forecast["unique_id"].unique()) == {"store_1", "store_2"}


def test_seasonal_naive_dates_are_future():
    history = _make_history()
    forecast = seasonal_naive_forecast(history, horizon=7)
    last_hist_date = history["ds"].max()
    assert (forecast["ds"] > last_hist_date).all()
