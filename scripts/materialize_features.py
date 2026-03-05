"""Materialize features from offline store to online store (Feast)."""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import FEATURE_REPO


def materialize():
    from feast import FeatureStore
    store = FeatureStore(repo_path=str(FEATURE_REPO))

    end_date = datetime.now()
    start_date = end_date - timedelta(days=400)

    print(f"Materializing features from {start_date} to {end_date}...")
    store.materialize(start_date=start_date, end_date=end_date)
    print("Done.")


if __name__ == "__main__":
    materialize()
