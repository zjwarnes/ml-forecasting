"""API routes for monitoring, actuals ingestion, drift history, and audit."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


class ActualsSubmission(BaseModel):
    prediction_id: str
    actuals: list[dict]


@router.post("/actuals")
def submit_actuals(submission: ActualsSubmission):
    """Submit actual values for a past prediction (log-and-join)."""
    from src.prediction_store import join_actuals
    result = join_actuals(submission.prediction_id, submission.actuals)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Prediction '{submission.prediction_id}' not found.")
    return result


@router.get("/drift/history")
def drift_history(limit: int = 30):
    """Return recent drift check results from the persistent log."""
    from src.monitor_scheduler import get_drift_history
    return {"records": get_drift_history(limit)}


@router.get("/drift/feature/{feature_name}")
def feature_drift_timeline(feature_name: str, limit: int = 50):
    """Get drift p-values for a specific feature over time."""
    from src.audit import get_feature_drift_timeline
    return {"feature": feature_name, "timeline": get_feature_drift_timeline(feature_name, limit)}


@router.get("/accuracy/history")
def accuracy_history(limit: int = 30):
    """Return recent accuracy metrics from joined predictions."""
    from src.prediction_store import get_accuracy_history
    return {"records": get_accuracy_history(limit)}


@router.get("/audit")
def audit_log(limit: int = 50, action: str | None = None):
    """Return recent audit log entries."""
    from src.audit import read_audit_log
    return {"records": read_audit_log(limit, action_filter=action)}


@router.get("/unjoined")
def unjoined_predictions(older_than_days: int = 7):
    """Find predictions that should have actuals by now but don't."""
    from src.prediction_store import get_unjoined_predictions
    return {"records": get_unjoined_predictions(older_than_days)}
