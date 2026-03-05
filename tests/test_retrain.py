"""Tests for retrain triggers."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timedelta
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_should_retrain_drift(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "DRIFT_LOG", tmp_path / "drift.jsonl")
    monkeypatch.setattr(settings, "LIFECYCLE_DB", tmp_path / "lifecycle.json")

    # Write a drift record
    drift_log = tmp_path / "drift.jsonl"
    drift_log.write_text(json.dumps({"drifted": True, "timestamp": datetime.now().isoformat()}) + "\n")

    from src.retrain import should_retrain
    needs, reason = should_retrain(check_drift=True, check_schedule=False)
    assert needs is True
    assert reason == "drift_detected"


def test_should_retrain_stale_model(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "DRIFT_LOG", tmp_path / "drift.jsonl")
    monkeypatch.setattr(settings, "LIFECYCLE_DB", tmp_path / "lifecycle.json")

    # Write a lifecycle with old promotion date
    old_date = (datetime.now() - timedelta(days=10)).isoformat()
    lifecycle = {"production": {"run_id": "old", "model_name": "M", "promoted_at": old_date}, "history": []}
    (tmp_path / "lifecycle.json").write_text(json.dumps(lifecycle))

    from src.retrain import should_retrain
    needs, reason = should_retrain(check_drift=False, check_schedule=True, max_age_days=7)
    assert needs is True
    assert "model_stale" in reason


def test_no_retrain_needed(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "DRIFT_LOG", tmp_path / "drift.jsonl")
    monkeypatch.setattr(settings, "LIFECYCLE_DB", tmp_path / "lifecycle.json")

    # No drift log, no lifecycle
    from src.retrain import should_retrain
    needs, reason = should_retrain()
    assert needs is False
