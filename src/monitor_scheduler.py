"""Scheduled monitoring: drift checks with persistent JSONL logging and alerting."""

import json
import logging
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import DRIFT_LOG, FEATURES_PARQUET, ALERT_WEBHOOK_URL
from src.monitor import run_drift_check

logger = logging.getLogger("monitor_scheduler")


def run_scheduled_monitoring(data_path: Path = FEATURES_PARQUET) -> dict:
    """Run drift check and append results to persistent log.

    Returns the drift record.
    """
    result = run_drift_check(data_path)

    record = {
        "timestamp": datetime.now().isoformat(),
        "drifted": result["drifted"],
        "details": result["details"],
    }

    DRIFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DRIFT_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")

    if result["drifted"]:
        fire_alert("drift_detected", record)

    return record


def fire_alert(alert_type: str, payload: dict):
    """Extensible alerting. Sends to webhook if configured, otherwise logs."""
    message = f"ALERT [{alert_type}]: {json.dumps(payload, default=str)}"

    if ALERT_WEBHOOK_URL:
        try:
            import requests
            requests.post(ALERT_WEBHOOK_URL, json={"text": message}, timeout=5)
            logger.info(f"Alert sent to webhook: {alert_type}")
        except Exception as e:
            logger.warning(f"Failed to send webhook alert: {e}")
    else:
        logger.warning(message)
        print(f"  ALERT: {alert_type} (no webhook configured, logged locally)")


def get_drift_history(limit: int = 50) -> list[dict]:
    """Read recent drift check results from persistent log."""
    if not DRIFT_LOG.exists():
        return []
    lines = DRIFT_LOG.read_text().strip().split("\n")
    records = [json.loads(line) for line in lines if line]
    return records[-limit:]


if __name__ == "__main__":
    run_scheduled_monitoring()
