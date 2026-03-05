"""Tests for feature registry."""

import pandas as pd
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.feature_registry import FeatureRegistry, FeatureDefinition


def _make_df():
    return pd.DataFrame({
        "y": [10.0, 20.0, 30.0, 40.0, 50.0],
        "ds": pd.date_range("2024-01-01", periods=5),
    })


def test_register_and_compute():
    registry = FeatureRegistry()
    registry.register(FeatureDefinition(
        name="y_doubled",
        compute_fn=lambda df: df["y"] * 2,
        dependencies=["y"],
    ))
    df = registry.compute_all(_make_df())
    assert "y_doubled" in df.columns
    assert df["y_doubled"].tolist() == [20.0, 40.0, 60.0, 80.0, 100.0]


def test_compute_missing_skips_existing():
    registry = FeatureRegistry()
    registry.register(FeatureDefinition(
        name="y_doubled",
        compute_fn=lambda df: df["y"] * 2,
    ))
    df = _make_df()
    df["y_doubled"] = [1, 2, 3, 4, 5]  # pre-existing column

    result = registry.compute_missing(df)
    # Should NOT overwrite existing column
    assert result["y_doubled"].tolist() == [1, 2, 3, 4, 5]


def test_get_missing():
    registry = FeatureRegistry()
    registry.register(FeatureDefinition(name="feat_a", compute_fn=lambda df: df["y"]))
    registry.register(FeatureDefinition(name="feat_b", compute_fn=lambda df: df["y"]))

    df = _make_df()
    df["feat_a"] = 0
    assert registry.get_missing(df) == ["feat_b"]
