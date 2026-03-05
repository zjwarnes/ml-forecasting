"""Data drift detection and proxy monitoring.

Monitors input feature distributions as an early warning for accuracy drops.
Instead of waiting 7 days for actuals, detect distribution shifts today.
"""

import pandas as pd
import numpy as np
from scipy import stats
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import FEATURES_PARQUET, TRAIN_CUTOFF, DRIFT_THRESHOLD


def detect_drift(
    reference_df: pd.DataFrame,
    current_df: pd.DataFrame,
    features: list[str] | None = None,
    threshold: float = DRIFT_THRESHOLD,
) -> dict:
    """Compare distributions of features between reference and current data.

    Uses Kolmogorov-Smirnov test for numerical features.

    Args:
        reference_df: Training/baseline data.
        current_df: Recent/production data.
        features: Columns to check. If None, checks all numeric columns.
        threshold: p-value below which drift is flagged.

    Returns:
        {"drifted": bool, "details": {feature: {statistic, p_value, drifted}}}
    """
    if features is None:
        features = reference_df.select_dtypes(include=[np.number]).columns.tolist()
        features = [f for f in features if f in current_df.columns]

    details = {}
    any_drift = False

    for feat in features:
        ref_vals = reference_df[feat].dropna().values
        cur_vals = current_df[feat].dropna().values

        if len(ref_vals) == 0 or len(cur_vals) == 0:
            details[feat] = {"statistic": None, "p_value": None, "drifted": False, "reason": "insufficient data"}
            continue

        stat, p_value = stats.ks_2samp(ref_vals, cur_vals)
        drifted = p_value < threshold
        if drifted:
            any_drift = True

        details[feat] = {
            "statistic": round(stat, 4),
            "p_value": round(p_value, 4),
            "drifted": drifted,
        }

    return {"drifted": any_drift, "details": details}


def run_drift_check(data_path: Path = FEATURES_PARQUET) -> dict:
    """Split data at TRAIN_CUTOFF and check for drift between train/test periods."""
    df = pd.read_parquet(data_path)
    cutoff = pd.Timestamp(TRAIN_CUTOFF)

    reference = df[df["ds"] < cutoff]
    current = df[df["ds"] >= cutoff]

    monitor_features = [
        "y", "rolling_sales_7d", "rolling_sales_28d",
        "lag_7", "lag_14", "day_of_week", "is_weekend",
    ]
    monitor_features = [f for f in monitor_features if f in df.columns]

    result = detect_drift(reference, current, features=monitor_features)

    print("\n=== Drift Report ===")
    print(f"  Overall drift detected: {result['drifted']}")
    for feat, info in result["details"].items():
        flag = " ** DRIFT **" if info.get("drifted") else ""
        p = info.get("p_value", "N/A")
        print(f"  {feat}: p_value={p}{flag}")

    return result


if __name__ == "__main__":
    run_drift_check()
