"""Audit log reader: query model promotions, retrains, drift history."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings


def read_audit_log(limit: int = 50, action_filter: str | None = None) -> list[dict]:
    """Read recent audit log entries.

    Args:
        limit: Max entries to return.
        action_filter: If set, only return entries with this action type.
    """
    if not settings.AUDIT_LOG.exists():
        return []
    lines = settings.AUDIT_LOG.read_text().strip().split("\n")
    records = [json.loads(line) for line in lines if line]
    if action_filter:
        records = [r for r in records if r.get("action") == action_filter]
    return records[-limit:]


def read_drift_history(limit: int = 50) -> list[dict]:
    """Read recent drift check results."""
    if not settings.DRIFT_LOG.exists():
        return []
    lines = settings.DRIFT_LOG.read_text().strip().split("\n")
    records = [json.loads(line) for line in lines if line]
    return records[-limit:]


def get_feature_drift_timeline(feature_name: str, limit: int = 50) -> list[dict]:
    """Get drift p-values for a specific feature over time."""
    history = read_drift_history(limit=limit)
    timeline = []
    for record in history:
        feat_info = record.get("details", {}).get(feature_name)
        if feat_info:
            timeline.append({
                "timestamp": record["timestamp"],
                "p_value": feat_info.get("p_value"),
                "drifted": feat_info.get("drifted"),
            })
    return timeline
