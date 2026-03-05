"""Tests for audit log reader."""

import json
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_read_empty_audit(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "AUDIT_LOG", tmp_path / "audit.jsonl")

    from src.audit import read_audit_log
    assert read_audit_log() == []


def test_read_audit_with_filter(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "AUDIT_LOG", tmp_path / "audit.jsonl")

    audit = tmp_path / "audit.jsonl"
    audit.write_text(
        json.dumps({"action": "promote", "model": "A"}) + "\n"
        + json.dumps({"action": "rollback", "model": "B"}) + "\n"
        + json.dumps({"action": "promote", "model": "C"}) + "\n"
    )

    from src.audit import read_audit_log
    all_records = read_audit_log()
    assert len(all_records) == 3

    promotes = read_audit_log(action_filter="promote")
    assert len(promotes) == 2


def test_drift_history(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "DRIFT_LOG", tmp_path / "drift.jsonl")

    drift = tmp_path / "drift.jsonl"
    drift.write_text(
        json.dumps({"timestamp": "t1", "drifted": False, "details": {"y": {"p_value": 0.5, "drifted": False}}}) + "\n"
        + json.dumps({"timestamp": "t2", "drifted": True, "details": {"y": {"p_value": 0.01, "drifted": True}}}) + "\n"
    )

    from src.audit import read_drift_history, get_feature_drift_timeline
    history = read_drift_history()
    assert len(history) == 2

    timeline = get_feature_drift_timeline("y")
    assert len(timeline) == 2
    assert timeline[1]["drifted"] is True
