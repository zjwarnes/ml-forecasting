"""Tests for experiment framework."""

import pandas as pd
import numpy as np
import pytest
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.experiment import run_experiment, ExperimentConfig


def _make_data(n_days=90, n_stores=2):
    rows = []
    rng = np.random.default_rng(42)
    for store in [f"store_{i}" for i in range(n_stores)]:
        dates = pd.date_range("2024-01-01", periods=n_days, freq="D")
        for d in dates:
            rows.append({"unique_id": store, "ds": d, "y": float(rng.uniform(50, 200))})
    return pd.DataFrame(rows)


def test_experiment_runs_and_saves_report(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "EXPERIMENTS_DIR", tmp_path / "experiments")

    df = _make_data()
    config = ExperimentConfig(
        name="test_exp",
        description="Test experiment",
        model_configs=[
            {"model_type": "SeasonalNaive", "params": {}},
        ],
        backtest_config={"horizon": 7, "n_splits": 2},
    )
    report = run_experiment(config, df)

    assert report["name"] == "test_exp"
    assert report["winner"] == "SeasonalNaive"
    assert len(report["results"]) == 1

    # Report file should exist
    report_path = tmp_path / "experiments" / f"{report['experiment_id']}.json"
    assert report_path.exists()


def test_experiment_picks_winner(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "EXPERIMENTS_DIR", tmp_path / "experiments")

    df = _make_data()
    config = ExperimentConfig(
        name="comparison",
        description="Compare two models",
        model_configs=[
            {"model_type": "SeasonalNaive", "params": {}},
            {"model_type": "SeasonalNaive", "params": {"season_length": 14}},
        ],
        backtest_config={"horizon": 7, "n_splits": 2},
    )
    report = run_experiment(config, df)

    assert report["winner"] in ["SeasonalNaive"]
    assert report["winner_wape"] > 0
    assert len(report["results"]) == 2
