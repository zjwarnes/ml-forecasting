"""End-to-end pipeline: generate data -> engineer features -> train -> evaluate -> monitor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    print("=" * 60)
    print("  DEMAND FORECAST PIPELINE")
    print("=" * 60)

    # Step 1: Generate data
    print("\n[1/7] Generating synthetic sales data...")
    from src.data_generator import generate_sales_data
    df = generate_sales_data()

    # Step 2: Data quality gate
    print("\n[2/7] Running data quality checks...")
    from src.data_quality import run_quality_checks
    report = run_quality_checks(df)
    print(f"  {report.summary()}")
    if not report.passed:
        print("  WARNING: Data quality issues detected. Continuing with caution.")

    # Step 3: Engineer features
    print("\n[3/7] Engineering features...")
    from src.feature_engineering import engineer_features
    engineer_features()

    # Step 4: Train all models
    print("\n[4/7] Training models...")
    from src.train import train_all_models
    results = train_all_models()

    # Step 5: Evaluate and promote champion
    print("\n[5/7] Evaluating models...")
    from src.evaluate import evaluate_and_promote
    evaluation = evaluate_and_promote(results)

    # Step 6: Promote champion via lifecycle
    print("\n[6/7] Updating model lifecycle...")
    from src.model_lifecycle import promote, ModelStage
    promote(
        run_id=evaluation["champion_run_id"],
        model_name=evaluation["champion"],
        to_stage=ModelStage.PRODUCTION,
        reason="pipeline_auto_promote",
    )

    # Step 7: Run drift check
    print("\n[7/7] Running drift detection...")
    from src.monitor import run_drift_check
    drift = run_drift_check()

    # Summary
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  Champion: {evaluation['champion']}")
    print(f"  WAPE: {evaluation['metrics']['wape']}")
    print(f"  Fallback active: {evaluation['fallback_active']}")
    print(f"  Drift detected: {drift['drifted']}")
    print(f"\n  Next: run 'make serve' to start the API")
    print("=" * 60)


if __name__ == "__main__":
    main()
