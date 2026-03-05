"""Tests for model lifecycle management."""

import pytest
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_promote_and_read(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "LIFECYCLE_DB", tmp_path / "lifecycle.json")
    monkeypatch.setattr(settings, "AUDIT_LOG", tmp_path / "audit.jsonl")

    from src.model_lifecycle import promote, get_current_state, get_production_model, ModelStage

    promote("run_abc", "AutoETS", ModelStage.PRODUCTION, "test_promote")

    state = get_current_state()
    assert state["production"]["model_name"] == "AutoETS"
    assert state["production"]["run_id"] == "run_abc"

    prod = get_production_model()
    assert prod["model_name"] == "AutoETS"


def test_rollback(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "LIFECYCLE_DB", tmp_path / "lifecycle.json")
    monkeypatch.setattr(settings, "AUDIT_LOG", tmp_path / "audit.jsonl")

    from src.model_lifecycle import promote, rollback, get_production_model, ModelStage

    promote("run_1", "ModelA", ModelStage.PRODUCTION, "first")
    promote("run_2", "ModelB", ModelStage.PRODUCTION, "second")

    assert get_production_model()["model_name"] == "ModelB"

    rollback("performance_degradation")
    assert get_production_model()["model_name"] == "ModelA"


def test_rollback_no_history(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "LIFECYCLE_DB", tmp_path / "lifecycle.json")
    monkeypatch.setattr(settings, "AUDIT_LOG", tmp_path / "audit.jsonl")

    from src.model_lifecycle import rollback
    with pytest.raises(ValueError, match="No previous model"):
        rollback("test")


def test_audit_log_written(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "LIFECYCLE_DB", tmp_path / "lifecycle.json")
    monkeypatch.setattr(settings, "AUDIT_LOG", tmp_path / "audit.jsonl")

    from src.model_lifecycle import promote, ModelStage

    promote("run_x", "TestModel", ModelStage.STAGING, "experiment")

    audit = tmp_path / "audit.jsonl"
    assert audit.exists()
    records = [json.loads(line) for line in audit.read_text().strip().split("\n")]
    assert len(records) == 1
    assert records[0]["action"] == "promote"
    assert records[0]["model_name"] == "TestModel"
