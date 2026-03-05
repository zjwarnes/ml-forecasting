"""Tests for data generation and feature engineering."""

import pandas as pd
import pytest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_generate_data_shape():
    from src.data_generator import generate_sales_data

    with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
        df = generate_sales_data(
            stores=["s1", "s2"], start="2024-01-01", end="2024-01-31",
            output_path=Path(f.name),
        )
    assert len(df) == 2 * 31  # 2 stores * 31 days
    assert set(df.columns) >= {"unique_id", "ds", "y", "store_id", "event_timestamp"}


def test_generate_data_no_nulls():
    from src.data_generator import generate_sales_data

    with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
        df = generate_sales_data(
            stores=["s1"], start="2024-01-01", end="2024-03-01",
            output_path=Path(f.name),
        )
    assert df.isnull().sum().sum() == 0


def test_generate_data_non_negative():
    from src.data_generator import generate_sales_data

    with tempfile.NamedTemporaryFile(suffix=".parquet") as f:
        df = generate_sales_data(
            stores=["s1", "s2", "s3"], start="2024-01-01", end="2024-12-31",
            output_path=Path(f.name),
        )
    assert (df["y"] >= 0).all()


def test_feature_engineering():
    from src.data_generator import generate_sales_data
    from src.feature_engineering import engineer_features

    with tempfile.TemporaryDirectory() as tmpdir:
        sales_path = Path(tmpdir) / "sales.parquet"
        feat_path = Path(tmpdir) / "features.parquet"

        generate_sales_data(
            stores=["s1"], start="2024-01-01", end="2024-03-01",
            output_path=sales_path,
        )
        df = engineer_features(input_path=sales_path, output_path=feat_path)

    expected_cols = {"rolling_sales_7d", "rolling_sales_28d", "lag_7", "lag_14",
                     "day_of_week", "month", "is_weekend"}
    assert expected_cols.issubset(set(df.columns))
    assert df.isnull().sum().sum() == 0
