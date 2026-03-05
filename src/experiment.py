"""Experiment framework: compare model configs with controlled backtests."""

import json
import hashlib
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings
from config.settings import SALES_PARQUET, MLFLOW_TRACKING_URI, EXPERIMENT_NAME
from src.backtest import run_backtest, BacktestConfig


@dataclass
class ExperimentConfig:
    name: str
    description: str
    model_configs: list[dict]  # each: {"model_type": str, "params": dict}
    backtest_config: dict | None = None  # BacktestConfig fields
    data_version: str | None = None  # batch_id or hash for traceability


def run_experiment(
    config: ExperimentConfig,
    df: pd.DataFrame,
) -> dict:
    """Run an experiment: backtest each model config, compare, save report.

    Saves results to EXPERIMENTS_DIR/<experiment_id>.json.

    Returns:
        {
            "experiment_id": str,
            "name": str,
            "results": [{"model_type": str, "params": dict, "aggregate": dict}],
            "winner": str,
            "winner_wape": float,
        }
    """
    experiment_id = hashlib.sha256(
        json.dumps(asdict(config), default=str).encode()
    ).hexdigest()[:12]

    bt_config = BacktestConfig(**(config.backtest_config or {}))

    print(f"\n{'='*60}")
    print(f"  EXPERIMENT: {config.name} ({experiment_id})")
    print(f"  {config.description}")
    print(f"{'='*60}")

    model_results = []
    for mc in config.model_configs:
        model_type = mc["model_type"]
        params = mc.get("params", {})
        print(f"\n--- {model_type} (params={params}) ---")

        bt_result = run_backtest(df, model_type, config=bt_config, params=params)
        model_results.append({
            "model_type": model_type,
            "params": params,
            "aggregate": bt_result["aggregate"],
            "per_split": bt_result["per_split"],
        })

    # Rank by mean WAPE
    ranked = sorted(model_results, key=lambda x: x["aggregate"]["mean_wape"])
    winner = ranked[0]

    report = {
        "experiment_id": experiment_id,
        "name": config.name,
        "description": config.description,
        "timestamp": datetime.now().isoformat(),
        "data_version": config.data_version,
        "backtest_config": asdict(bt_config),
        "results": [
            {"model_type": r["model_type"], "params": r["params"], "aggregate": r["aggregate"]}
            for r in ranked
        ],
        "winner": winner["model_type"],
        "winner_wape": winner["aggregate"]["mean_wape"],
    }

    # Save report
    settings.EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = settings.EXPERIMENTS_DIR / f"{experiment_id}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))

    print(f"\n=== EXPERIMENT RESULTS ===")
    for i, r in enumerate(ranked):
        tag = " << WINNER" if i == 0 else ""
        print(f"  #{i+1} {r['model_type']}: mean_WAPE={r['aggregate']['mean_wape']}{tag}")
    print(f"\nReport saved: {report_path}")

    return report


if __name__ == "__main__":
    df = pd.read_parquet(SALES_PARQUET)
    df = df[["unique_id", "ds", "y"]]

    config = ExperimentConfig(
        name="baseline_comparison",
        description="Compare SeasonalNaive vs AutoETS with default params",
        model_configs=[
            {"model_type": "SeasonalNaive", "params": {}},
            {"model_type": "AutoETS", "params": {"season_length": 7}},
        ],
    )
    run_experiment(config, df)
