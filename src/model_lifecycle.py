"""Model lifecycle: staging/shadow/production promotion flow with rollback."""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings


class ModelStage(str, Enum):
    STAGING = "staging"
    SHADOW = "shadow"
    PRODUCTION = "production"
    ARCHIVED = "archived"


def get_current_state() -> dict:
    """Read the current model lifecycle state."""
    if settings.LIFECYCLE_DB.exists():
        return json.loads(settings.LIFECYCLE_DB.read_text())
    return {"production": None, "shadow": None, "staging": None, "history": []}


def promote(run_id: str, model_name: str, to_stage: ModelStage, reason: str) -> dict:
    """Promote a model to a new stage. Logs to audit trail.

    If promoting to production, the current production model is archived.
    """
    state = get_current_state()

    # Archive current occupant of the target stage
    if to_stage == ModelStage.PRODUCTION and state.get("production"):
        old = state["production"]
        old["archived_at"] = datetime.now().isoformat()
        state.setdefault("history", []).append(old)

    entry = {
        "run_id": run_id,
        "model_name": model_name,
        "promoted_at": datetime.now().isoformat(),
        "reason": reason,
    }
    state[to_stage.value] = entry

    settings.LIFECYCLE_DB.parent.mkdir(parents=True, exist_ok=True)
    settings.LIFECYCLE_DB.write_text(json.dumps(state, indent=2))
    _log_audit("promote", run_id=run_id, model_name=model_name, to_stage=to_stage.value, reason=reason)

    print(f"  Promoted {model_name} ({run_id[:8]}...) to {to_stage.value}: {reason}")
    return entry


def rollback(reason: str) -> dict:
    """Rollback production to the previous model in history.

    Returns the restored model entry.
    """
    state = get_current_state()
    history = state.get("history", [])

    if not history:
        raise ValueError("No previous model to rollback to.")

    previous = history.pop()
    if state.get("production"):
        state["history"].append({
            **state["production"],
            "archived_at": datetime.now().isoformat(),
        })

    state["production"] = previous
    settings.LIFECYCLE_DB.write_text(json.dumps(state, indent=2))
    _log_audit("rollback", reason=reason, restored_run_id=previous["run_id"],
               restored_model=previous["model_name"])

    print(f"  Rolled back to {previous['model_name']} ({previous['run_id'][:8]}...): {reason}")
    return previous


def get_production_model() -> dict | None:
    """Get the current production model entry."""
    state = get_current_state()
    return state.get("production")


def _log_audit(action: str, **kwargs):
    """Append to the persistent audit log."""
    record = {"timestamp": datetime.now().isoformat(), "action": action, **kwargs}
    settings.AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.AUDIT_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")
