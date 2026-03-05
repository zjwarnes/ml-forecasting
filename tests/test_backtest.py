"""Tests for backtesting framework."""

import pandas as pd
import numpy as np
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.backtest import generate_splits, BacktestConfig


def _make_data(n_days=120, n_stores=2):
    rows = []
    for store in [f"store_{i}" for i in range(n_stores)]:
        dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
        for d in dates:
            rows.append({"unique_id": store, "ds": d, "y": float(np.random.randint(50, 200))})
    return pd.DataFrame(rows)


def test_expanding_splits_no_leakage():
    df = _make_data(n_days=120, n_stores=1)
    config = BacktestConfig(horizon=7, n_splits=3, strategy="expanding")
    splits = generate_splits(df, config)

    assert len(splits) == 3
    for train, test in splits:
        assert train["ds"].max() < test["ds"].min(), "Train data must precede test data"


def test_sliding_splits_no_leakage():
    df = _make_data(n_days=120, n_stores=1)
    config = BacktestConfig(horizon=7, n_splits=3, strategy="sliding", window_size=30)
    splits = generate_splits(df, config)

    assert len(splits) == 3
    for train, test in splits:
        assert train["ds"].max() < test["ds"].min()
        # Sliding window should have bounded train size
        train_days = train["ds"].nunique()
        assert train_days <= 30


def test_correct_number_of_splits():
    df = _make_data(n_days=200, n_stores=1)
    for n in [2, 4, 6]:
        config = BacktestConfig(horizon=7, n_splits=n)
        splits = generate_splits(df, config)
        assert len(splits) == n


def test_insufficient_data_raises():
    df = _make_data(n_days=10, n_stores=1)
    config = BacktestConfig(horizon=7, n_splits=4)
    with pytest.raises(ValueError, match="Not enough data"):
        generate_splits(df, config)


def test_gap_between_train_and_test():
    df = _make_data(n_days=120, n_stores=1)
    config = BacktestConfig(horizon=7, n_splits=2, gap=3)
    splits = generate_splits(df, config)

    for train, test in splits:
        gap_days = (test["ds"].min() - train["ds"].max()).days
        assert gap_days >= 4  # at least gap+1 days between train end and test start
