"""Champion/challenger evaluation: pick the best model, enforce performance gates."""

import mlflow
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    WAPE_THRESHOLD, MLFLOW_TRACKING_URI, EXPERIMENT_NAME, MODEL_REGISTRY_NAME,
)


def evaluate_and_promote(results: dict) -> dict:
    """Pick champion from training results. Apply performance gates.

    Args:
        results: Dict from train.train_all_models()
            {model_name: {"metrics": {...}, "run_id": str}}

    Returns:
        {"champion": str, "metrics": dict, "fallback_active": bool}
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    # Sort by WAPE (lower is better)
    ranked = sorted(results.items(), key=lambda x: x[1]["metrics"]["wape"])

    print("\n=== Champion/Challenger Ranking ===")
    for rank, (name, r) in enumerate(ranked, 1):
        tag = ""
        if rank == 1:
            tag = " << CHAMPION"
        print(f"  #{rank} {name}: WAPE={r['metrics']['wape']}{tag}")

    best_name, best = ranked[0]
    fallback_active = False

    # ── Performance Gate ───────────────────────────────────────────────
    if best["metrics"]["wape"] > WAPE_THRESHOLD:
        print(f"\n  ALERT: Best model WAPE ({best['metrics']['wape']}) exceeds threshold ({WAPE_THRESHOLD})")
        print("  Activating SeasonalNaive fallback as champion.")

        # Force fallback
        if "SeasonalNaive" in results:
            best_name = "SeasonalNaive"
            best = results["SeasonalNaive"]
        fallback_active = True

    # ── Tag in MLflow ──────────────────────────────────────────────────
    for name, r in results.items():
        client = mlflow.tracking.MlflowClient()
        tag = "champion" if name == best_name else "challenger"
        client.set_tag(r["run_id"], "model_status", tag)
        client.set_tag(r["run_id"], "model_name", name)

    print(f"\n  Champion: {best_name} (tagged in MLflow)")
    print(f"  Fallback active: {fallback_active}")

    return {
        "champion": best_name,
        "champion_run_id": best["run_id"],
        "metrics": best["metrics"],
        "fallback_active": fallback_active,
        "ranking": {name: r["metrics"] for name, r in ranked},
    }
