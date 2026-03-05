"""Tests for incremental data ingestion."""

import pandas as pd
import pytest
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _make_batch(store="s1", start="2024-01-01", days=5):
    dates = pd.date_range(start, periods=days, freq="D")
    return pd.DataFrame({
        "unique_id": store,
        "ds": dates,
        "y": range(10, 10 + days),
        "store_id": store,
        "event_timestamp": dates,
    })


def test_append_batch_creates_file(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "INGEST_MANIFEST", tmp_path / "manifest.jsonl")

    from src.data_ingest import append_batch
    out = tmp_path / "sales.parquet"
    batch = _make_batch()
    record = append_batch(batch, existing_path=out, batch_id="test_1")

    assert out.exists()
    assert record["rows_added"] == 5
    assert record["total_rows"] == 5
    assert record["batch_id"] == "test_1"


def test_append_batch_deduplicates(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "INGEST_MANIFEST", tmp_path / "manifest.jsonl")

    from src.data_ingest import append_batch
    out = tmp_path / "sales.parquet"

    batch1 = _make_batch(start="2024-01-01", days=5)
    append_batch(batch1, existing_path=out, batch_id="b1")

    # Overlapping batch — 3 days overlap, 2 new
    batch2 = _make_batch(start="2024-01-04", days=4)
    record = append_batch(batch2, existing_path=out, batch_id="b2")

    df = pd.read_parquet(out)
    # Jan 1-5 (5 days) + Jan 4-7 (4 days) with 2 overlapping (Jan 4, Jan 5) = 7 unique
    assert len(df) == 7


def test_manifest_tracks_batches(tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "INGEST_MANIFEST", tmp_path / "manifest.jsonl")

    from src.data_ingest import append_batch, get_ingest_history
    out = tmp_path / "sales.parquet"

    append_batch(_make_batch(), existing_path=out, batch_id="b1")
    append_batch(_make_batch(start="2024-02-01"), existing_path=out, batch_id="b2")

    history = get_ingest_history()
    assert len(history) == 2
    assert history[0]["batch_id"] == "b1"
    assert history[1]["batch_id"] == "b2"
