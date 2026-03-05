"""Time-series cross-validation: expanding and sliding window backtests."""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import FORECAST_HORIZON, SEASON_LENGTH, SALES_PARQUET
from src.train import compute_metrics, train_single_model


@dataclass
class BacktestConfig:
    horizon: int = FORECAST_HORIZON
    n_splits: int = 4
    strategy: str = "expanding"  # "expanding" or "sliding"
    window_size: int | None = None  # only for sliding; None = use all history
    gap: int = 0  # days between train end and test start


def generate_splits(
    df: pd.DataFrame,
    config: BacktestConfig,
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """Generate train/test splits for time-series CV.

    Returns list of (train_df, test_df) tuples.
    Guarantees: all train dates < all test dates (no leakage).
    """
    dates = sorted(df["ds"].unique())
    total = len(dates)

    # Need enough dates for n_splits * horizon at the tail
    test_dates_needed = config.n_splits * config.horizon
    earliest_cutoff_idx = total - test_dates_needed

    if earliest_cutoff_idx < config.horizon:
        raise ValueError(
            f"Not enough data for {config.n_splits} splits of {config.horizon} days. "
            f"Need at least {test_dates_needed + config.horizon} unique dates, got {total}."
        )

    splits = []
    for i in range(config.n_splits):
        test_start_idx = earliest_cutoff_idx + i * config.horizon
        test_end_idx = min(test_start_idx + config.horizon, total)

        cutoff_idx = test_start_idx - 1 - config.gap
        cutoff_date = dates[cutoff_idx]
        test_dates_range = dates[test_start_idx:test_end_idx]

        if config.strategy == "expanding":
            train = df[df["ds"] <= cutoff_date].copy()
        else:  # sliding
            window = config.window_size or cutoff_idx + 1
            window_start_idx = max(0, cutoff_idx + 1 - window)
            window_start = dates[window_start_idx]
            train = df[(df["ds"] >= window_start) & (df["ds"] <= cutoff_date)].copy()

        test = df[df["ds"].isin(test_dates_range)].copy()
        splits.append((train, test))

    return splits


def run_backtest(
    df: pd.DataFrame,
    model_type: str,
    config: BacktestConfig | None = None,
    params: dict | None = None,
) -> dict:
    """Run a full backtest for a model across all CV splits.

    Returns:
        {
            "model_type": str,
            "config": dict,
            "per_split": [{"split": int, "metrics": dict}],
            "aggregate": {"mean_wape": float, "mean_mae": float, "mean_rmse": float},
        }
    """
    config = config or BacktestConfig()
    splits = generate_splits(df, config)

    per_split = []
    for i, (train, test) in enumerate(splits):
        result = train_single_model(
            model_type=model_type,
            train_df=train[["unique_id", "ds", "y"]],
            test_df=test[["unique_id", "ds", "y"]],
            params=params,
            horizon=config.horizon,
        )
        per_split.append({"split": i, "metrics": result["metrics"]})
        print(f"  Split {i}: {result['metrics']}")

    # Aggregate
    mean_wape = np.mean([s["metrics"]["wape"] for s in per_split])
    mean_mae = np.mean([s["metrics"]["mae"] for s in per_split])
    mean_rmse = np.mean([s["metrics"]["rmse"] for s in per_split])

    return {
        "model_type": model_type,
        "config": {
            "horizon": config.horizon,
            "n_splits": config.n_splits,
            "strategy": config.strategy,
        },
        "per_split": per_split,
        "aggregate": {
            "mean_wape": round(mean_wape, 4),
            "mean_mae": round(mean_mae, 4),
            "mean_rmse": round(mean_rmse, 4),
        },
    }


if __name__ == "__main__":
    df = pd.read_parquet(SALES_PARQUET)
    df = df[["unique_id", "ds", "y"]]

    for model in ["SeasonalNaive", "AutoETS"]:
        print(f"\n=== Backtest: {model} ===")
        result = run_backtest(df, model)
        print(f"  Aggregate: {result['aggregate']}")
