"""Compute time-series features with point-in-time correctness (no future leakage)."""

import pandas as pd
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import SALES_PARQUET, FEATURES_PARQUET, SEASON_LENGTH


def engineer_features(
    input_path: Path = SALES_PARQUET,
    output_path: Path = FEATURES_PARQUET,
    incremental: bool = False,
) -> pd.DataFrame:
    """Add rolling, lag, and calendar features grouped by store.

    All rolling/lag features use only past data (shift(1) before rolling)
    to prevent data leakage.

    Args:
        incremental: If True and output_path exists, only recompute for new rows.
    """
    df = pd.read_parquet(input_path)
    df = df.sort_values(["unique_id", "ds"]).reset_index(drop=True)

    # In incremental mode, check if we can skip (no new rows)
    if incremental and output_path.exists():
        existing = pd.read_parquet(output_path)
        existing_keys = set(zip(existing["unique_id"], existing["ds"]))
        new_keys = set(zip(df["unique_id"], df["ds"]))
        if new_keys.issubset(existing_keys):
            print("No new rows to process (incremental mode).")
            return existing

    # ── Rolling features (shifted to avoid leakage) ────────────────────
    grouped = df.groupby("unique_id")["y"]

    # shift(1) ensures we only use data available *before* the current row
    shifted = grouped.shift(1)
    df["rolling_sales_7d"] = shifted.rolling(7, min_periods=1).mean().values
    df["rolling_sales_28d"] = shifted.rolling(28, min_periods=1).mean().values

    # ── Lag features ───────────────────────────────────────────────────
    df["lag_7"] = grouped.shift(SEASON_LENGTH).values
    df["lag_14"] = grouped.shift(SEASON_LENGTH * 2).values

    # ── Calendar features ──────────────────────────────────────────────
    df["day_of_week"] = df["ds"].dt.dayofweek
    df["month"] = df["ds"].dt.month
    df["is_weekend"] = (df["ds"].dt.dayofweek >= 5).astype(int)

    # ── Fill NaNs from early rows (not enough history) ─────────────────
    for col in ["rolling_sales_7d", "rolling_sales_28d", "lag_7", "lag_14"]:
        df[col] = df.groupby("unique_id")[col].ffill().fillna(0)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"Engineered features -> {output_path} ({len(df)} rows, {len(df.columns)} cols)")
    return df


if __name__ == "__main__":
    engineer_features()
