"""Incremental data ingestion: append new batches without regenerating."""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings
from config.settings import SALES_PARQUET, DATA_DIR


def append_batch(
    new_data: pd.DataFrame,
    existing_path: Path = SALES_PARQUET,
    batch_id: str | None = None,
) -> dict:
    """Append a new data batch to the sales parquet.

    Deduplicates on (unique_id, ds). Later rows win.
    Records the batch in a JSONL manifest for traceability.

    Args:
        new_data: DataFrame with columns [unique_id, ds, y, store_id, event_timestamp].
        existing_path: Path to the existing sales parquet.
        batch_id: Optional identifier for this batch.

    Returns:
        Manifest record dict with batch_id, rows_added, total_rows, date_range.
    """
    batch_id = batch_id or datetime.now().strftime("%Y%m%d_%H%M%S")

    if existing_path.exists():
        existing = pd.read_parquet(existing_path)
        combined = pd.concat([existing, new_data], ignore_index=True)
        combined = combined.drop_duplicates(subset=["unique_id", "ds"], keep="last")
    else:
        combined = new_data

    combined = combined.sort_values(["unique_id", "ds"]).reset_index(drop=True)
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(existing_path, index=False)

    record = {
        "batch_id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "rows_added": len(new_data),
        "total_rows": len(combined),
        "date_range": [str(new_data["ds"].min()), str(new_data["ds"].max())],
    }
    settings.INGEST_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(settings.INGEST_MANIFEST, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(f"Ingested batch '{batch_id}': {len(new_data)} rows -> {len(combined)} total")
    return record


def get_ingest_history(limit: int = 50) -> list[dict]:
    """Read recent ingestion manifest entries."""
    if not settings.INGEST_MANIFEST.exists():
        return []
    lines = settings.INGEST_MANIFEST.read_text().strip().split("\n")
    records = [json.loads(line) for line in lines if line]
    return records[-limit:]
