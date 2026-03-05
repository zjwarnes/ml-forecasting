"""Training pipeline: AutoETS + MLP + SeasonalNaive with MLflow tracking."""

import mlflow
import pandas as pd
import numpy as np
from pathlib import Path
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    FEATURES_PARQUET, SALES_PARQUET, TRAIN_CUTOFF, EXPERIMENT_NAME,
    FORECAST_HORIZON, SEASON_LENGTH, INPUT_SIZE, MLP_CONFIG,
    MLFLOW_TRACKING_URI, MODEL_REGISTRY_NAME,
)


def compute_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    """Compute MAE, RMSE, and WAPE."""
    mae = np.mean(np.abs(actual - predicted))
    rmse = np.sqrt(np.mean((actual - predicted) ** 2))
    wape = np.sum(np.abs(actual - predicted)) / np.sum(np.abs(actual)) if np.sum(np.abs(actual)) > 0 else float("inf")
    return {"mae": round(mae, 4), "rmse": round(rmse, 4), "wape": round(wape, 4)}


def train_single_model(
    model_type: str,
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    params: dict | None = None,
    horizon: int = FORECAST_HORIZON,
) -> dict:
    """Train a single model and return predictions + metrics.

    Args:
        model_type: One of "SeasonalNaive", "AutoETS", "MLP".
        train_df: Training data with [unique_id, ds, y].
        test_df: Test data with [unique_id, ds, y].
        params: Model-specific parameters (overrides defaults).
        horizon: Forecast horizon.

    Returns:
        {"predictions": DataFrame, "metrics": dict, "model_type": str}
    """
    params = params or {}

    if model_type == "SeasonalNaive":
        from src.fallback import seasonal_naive_forecast
        season = params.get("season_length", SEASON_LENGTH)
        preds = seasonal_naive_forecast(train_df, horizon=horizon, season_length=season)
        pred_col = "SeasonalNaive"

    elif model_type == "AutoETS":
        from statsforecast import StatsForecast
        from statsforecast.models import AutoETS as AutoETSModel
        season = params.get("season_length", SEASON_LENGTH)
        sf = StatsForecast(models=[AutoETSModel(season_length=season)], freq="D", n_jobs=1)
        sf.fit(train_df)
        preds = sf.predict(h=horizon).reset_index()
        pred_col = "AutoETS"

    elif model_type == "MLP":
        from neuralforecast import NeuralForecast
        from neuralforecast.models import MLP
        from neuralforecast.losses.pytorch import MAE
        cfg = {**MLP_CONFIG, **params}
        model = MLP(
            h=cfg.get("h", horizon),
            input_size=cfg.get("input_size", INPUT_SIZE),
            hidden_size=cfg.get("hidden_size", 64),
            max_steps=cfg.get("max_steps", 200),
            loss=MAE(),
            accelerator=cfg.get("accelerator", "cpu"),
            enable_progress_bar=True,
        )
        nf = NeuralForecast(models=[model], freq="D")
        nf.fit(df=train_df)
        preds = nf.predict().reset_index()
        pred_col = "MLP"

    else:
        raise ValueError(f"Unknown model type: {model_type}")

    merged = test_df.merge(preds, on=["unique_id", "ds"], how="inner")
    if len(merged) > 0:
        metrics = compute_metrics(merged["y"].values, merged[pred_col].values)
    else:
        metrics = {"mae": float("inf"), "rmse": float("inf"), "wape": float("inf")}

    return {"predictions": preds, "metrics": metrics, "model_type": model_type, "pred_col": pred_col}


def train_all_models(data_path: Path = SALES_PARQUET) -> dict:
    """Train AutoETS, MLP, and SeasonalNaive. Log everything to MLflow.

    Returns dict of {model_name: {metrics, run_id}}.
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    df = pd.read_parquet(data_path)
    df = df[["unique_id", "ds", "y"]].sort_values(["unique_id", "ds"])

    cutoff = pd.Timestamp(TRAIN_CUTOFF)
    train_df = df[df["ds"] < cutoff].copy()
    test_df = df[df["ds"] >= cutoff].copy()

    # Only take the first FORECAST_HORIZON days per store for evaluation
    test_df = (
        test_df.groupby("unique_id")
        .head(FORECAST_HORIZON)
        .reset_index(drop=True)
    )

    results = {}

    # ── 1. SeasonalNaive (heuristic fallback) ──────────────────────────
    print("Training SeasonalNaive...")
    with mlflow.start_run(run_name="SeasonalNaive"):
        from src.fallback import seasonal_naive_forecast
        naive_preds = seasonal_naive_forecast(train_df, horizon=FORECAST_HORIZON)

        merged = test_df.merge(naive_preds, on=["unique_id", "ds"], how="inner")
        if len(merged) > 0:
            metrics = compute_metrics(merged["y"].values, merged["SeasonalNaive"].values)
        else:
            metrics = {"mae": float("inf"), "rmse": float("inf"), "wape": float("inf")}

        mlflow.log_params({"model_type": "SeasonalNaive", "season_length": SEASON_LENGTH})
        mlflow.log_metrics(metrics)
        results["SeasonalNaive"] = {"metrics": metrics, "run_id": mlflow.active_run().info.run_id}
        print(f"  SeasonalNaive metrics: {metrics}")

    # ── 2. AutoETS (statistical) ───────────────────────────────────────
    print("Training AutoETS...")
    with mlflow.start_run(run_name="AutoETS"):
        from statsforecast import StatsForecast
        from statsforecast.models import AutoETS as AutoETSModel

        sf = StatsForecast(
            models=[AutoETSModel(season_length=SEASON_LENGTH)],
            freq="D",
            n_jobs=1,
        )
        sf.fit(train_df)
        ets_preds = sf.predict(h=FORECAST_HORIZON)
        ets_preds = ets_preds.reset_index()

        merged = test_df.merge(ets_preds, on=["unique_id", "ds"], how="inner")
        if len(merged) > 0:
            metrics = compute_metrics(merged["y"].values, merged["AutoETS"].values)
        else:
            metrics = {"mae": float("inf"), "rmse": float("inf"), "wape": float("inf")}

        mlflow.log_params({"model_type": "AutoETS", "season_length": SEASON_LENGTH})
        mlflow.log_metrics(metrics)

        # Save the fitted model as artifact
        sf.save("autoets_model")
        mlflow.log_artifact("autoets_model")

        results["AutoETS"] = {"metrics": metrics, "run_id": mlflow.active_run().info.run_id}
        print(f"  AutoETS metrics: {metrics}")

    # ── 3. MLP (neural) ───────────────────────────────────────────────
    print("Training MLP...")
    with mlflow.start_run(run_name="MLP"):
        from neuralforecast import NeuralForecast
        from neuralforecast.models import MLP
        from neuralforecast.losses.pytorch import MAE

        model = MLP(
            h=MLP_CONFIG["h"],
            input_size=MLP_CONFIG["input_size"],
            hidden_size=MLP_CONFIG["hidden_size"],
            max_steps=MLP_CONFIG["max_steps"],
            loss=MAE(),
            accelerator=MLP_CONFIG["accelerator"],
            enable_progress_bar=True,
        )
        nf = NeuralForecast(models=[model], freq="D")
        nf.fit(df=train_df)
        mlp_preds = nf.predict()
        mlp_preds = mlp_preds.reset_index()

        merged = test_df.merge(mlp_preds, on=["unique_id", "ds"], how="inner")
        if len(merged) > 0:
            metrics = compute_metrics(merged["y"].values, merged["MLP"].values)
        else:
            metrics = {"mae": float("inf"), "rmse": float("inf"), "wape": float("inf")}

        mlflow.log_params({
            "model_type": "MLP",
            "hidden_size": MLP_CONFIG["hidden_size"],
            "input_size": MLP_CONFIG["input_size"],
            "max_steps": MLP_CONFIG["max_steps"],
        })
        mlflow.log_metrics(metrics)

        # Save NeuralForecast model as directory artifact
        # (avoids mlflow.pytorch.log_model which needs MLflow 3.x server)
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            nf.save(tmpdir)
            mlflow.log_artifacts(tmpdir, "mlp_model")

        results["MLP"] = {"metrics": metrics, "run_id": mlflow.active_run().info.run_id}
        print(f"  MLP metrics: {metrics}")

    # ── Log comparison summary ─────────────────────────────────────────
    print("\n=== Model Comparison ===")
    for name, r in results.items():
        print(f"  {name}: WAPE={r['metrics']['wape']}, MAE={r['metrics']['mae']}, RMSE={r['metrics']['rmse']}")

    return results


if __name__ == "__main__":
    train_all_models()
