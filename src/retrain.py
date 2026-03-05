"""Retrain orchestration: trigger retraining based on drift, schedule, or manual request."""

import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings


def should_retrain(
    check_drift: bool = True,
    check_schedule: bool = True,
    max_age_days: int = 7,
) -> tuple[bool, str]:
    """Determine if retraining is needed.

    Checks:
    1. Drift detected in latest monitoring run.
    2. Model age exceeds max_age_days.

    Returns (should_retrain, reason).
    """
    # Check drift log
    if check_drift and settings.DRIFT_LOG.exists():
        lines = settings.DRIFT_LOG.read_text().strip().split("\n")
        if lines:
            latest = json.loads(lines[-1])
            if latest.get("drifted"):
                return True, "drift_detected"

    # Check model age
    if check_schedule and settings.LIFECYCLE_DB.exists():
        state = json.loads(settings.LIFECYCLE_DB.read_text())
        prod = state.get("production")
        if prod and "promoted_at" in prod:
            promoted = datetime.fromisoformat(prod["promoted_at"])
            age = datetime.now() - promoted
            if age > timedelta(days=max_age_days):
                return True, f"model_stale_{age.days}d"

    return False, "no_trigger"


def trigger_retrain(reason: str = "manual"):
    """Execute a retrain: run the full pipeline.

    The pipeline handles data gen, features, training, evaluation, and promotion.
    """
    print(f"Triggering retrain: {reason}")
    from scripts.run_pipeline import main as run_pipeline
    run_pipeline()
    print(f"Retrain complete (reason: {reason})")


if __name__ == "__main__":
    needs, reason = should_retrain()
    if needs:
        print(f"Retrain needed: {reason}")
        trigger_retrain(reason)
    else:
        print(f"No retrain needed ({reason})")
