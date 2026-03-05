"""Tests for data quality gates."""

import pandas as pd
import numpy as np
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data_quality import run_quality_checks


def _make_clean_data(n=30):
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame({
        "unique_id": "store_1",
        "ds": dates,
        "y": np.random.default_rng(42).uniform(50, 200, n),
    })


def test_clean_data_passes():
    report = run_quality_checks(_make_clean_data())
    assert report.passed


def test_missing_columns_fails():
    df = pd.DataFrame({"x": [1, 2, 3]})
    report = run_quality_checks(df)
    assert not report.passed


def test_nulls_fail():
    df = _make_clean_data()
    df.loc[0:5, "y"] = None  # 20% nulls
    report = run_quality_checks(df)
    failed_checks = [c for c in report.checks if not c["passed"]]
    assert any("nulls_y" in c["check"] for c in failed_checks)


def test_negative_y_fails():
    df = _make_clean_data()
    df.loc[0, "y"] = -10
    report = run_quality_checks(df)
    failed_checks = [c for c in report.checks if not c["passed"]]
    assert any("non_negative" in c["check"] for c in failed_checks)


def test_gap_detection():
    dates = list(pd.date_range("2024-01-01", periods=10, freq="D"))
    dates.pop(5)  # Create a gap
    df = pd.DataFrame({
        "unique_id": "store_1",
        "ds": dates,
        "y": range(len(dates)),
    })
    report = run_quality_checks(df)
    failed_checks = [c for c in report.checks if not c["passed"]]
    assert any("continuity" in c["check"] for c in failed_checks)
