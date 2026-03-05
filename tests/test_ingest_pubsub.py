"""Tests for the /ingest/pubsub Pub/Sub push endpoint."""

import base64
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_redis_for_app():
    """Mock Redis so the app starts without a real Redis connection."""
    storage = {}

    class FakeRedis:
        def __init__(self, *a, **kw):
            pass

        def rpush(self, key, value):
            storage.setdefault(key, []).append(value)
            return len(storage[key])

        def llen(self, key):
            return len(storage.get(key, []))

        def lrange(self, key, start, end):
            items = storage.get(key, [])
            if end == -1:
                return items[start:]
            return items[start : end + 1]

        def delete(self, key):
            storage.pop(key, None)
            return 1

        def pipeline(self):
            return FakePipeline(storage)

    class FakePipeline:
        def __init__(self, storage):
            self._storage = storage
            self._commands = []

        def rpush(self, key, value):
            self._commands.append(("rpush", key, value))
            return self

        def lrange(self, key, start, end):
            self._commands.append(("lrange", key, start, end))
            return self

        def delete(self, key):
            self._commands.append(("delete", key))
            return self

        def execute(self):
            results = []
            for cmd in self._commands:
                if cmd[0] == "rpush":
                    self._storage.setdefault(cmd[1], []).append(cmd[2])
                    results.append(len(self._storage[cmd[1]]))
                elif cmd[0] == "lrange":
                    items = self._storage.get(cmd[1], [])
                    end = cmd[3]
                    if end == -1:
                        results.append(items[cmd[2] :])
                    else:
                        results.append(items[cmd[2] : end + 1])
                elif cmd[0] == "delete":
                    self._storage.pop(cmd[1], None)
                    results.append(1)
            self._commands = []
            return results

    fake = FakeRedis()
    with patch("src.stream_buffer._get_redis", return_value=fake):
        storage.clear()
        yield storage


@pytest.fixture
def client(mock_redis_for_app):
    from service.app import app

    with TestClient(app) as c:
        yield c


def _pubsub_envelope(payload: dict) -> dict:
    """Build a Pub/Sub push envelope from a payload dict."""
    data_b64 = base64.b64encode(json.dumps(payload).encode()).decode()
    return {"message": {"data": data_b64}, "subscription": "projects/test/subscriptions/test-sub"}


def test_pubsub_batch_records(client):
    """Valid Pub/Sub envelope with multiple records is ingested."""
    envelope = _pubsub_envelope(
        {
            "records": [
                {"unique_id": "store_1", "ds": "2024-06-15", "y": 142.5},
                {"unique_id": "store_2", "ds": "2024-06-15", "y": 200.0},
            ]
        }
    )
    resp = client.post("/ingest/pubsub", json=envelope)
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "pubsub"


def test_pubsub_single_record(client):
    """Valid Pub/Sub envelope with a single record (not wrapped in 'records')."""
    envelope = _pubsub_envelope({"unique_id": "store_1", "ds": "2024-06-16", "y": 155.0})
    resp = client.post("/ingest/pubsub", json=envelope)
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "pubsub"


def test_pubsub_invalid_base64(client):
    """Invalid base64 in message.data returns 400."""
    envelope = {"message": {"data": "not-valid-base64!!!"}, "subscription": "test"}
    resp = client.post("/ingest/pubsub", json=envelope)
    assert resp.status_code == 400
    assert "base64" in resp.json()["detail"].lower() or "Invalid" in resp.json()["detail"]


def test_pubsub_missing_data_field(client):
    """Envelope without message.data returns 400."""
    envelope = {"message": {}, "subscription": "test"}
    resp = client.post("/ingest/pubsub", json=envelope)
    assert resp.status_code == 400


def test_pubsub_empty_payload(client):
    """Envelope with valid base64 but no records returns 400."""
    envelope = _pubsub_envelope({"something": "irrelevant"})
    resp = client.post("/ingest/pubsub", json=envelope)
    assert resp.status_code == 400
    assert "No records" in resp.json()["detail"]


def test_pubsub_direct_mode(client, tmp_path, monkeypatch):
    """When PUBSUB_ENABLED=True, records write directly via append_batch."""
    import config.settings as settings

    monkeypatch.setattr(settings, "PUBSUB_ENABLED", True)

    parquet_path = tmp_path / "sales.parquet"
    monkeypatch.setattr(settings, "SALES_PARQUET", parquet_path)
    monkeypatch.setattr(settings, "INGEST_MANIFEST", tmp_path / "manifest.jsonl")

    envelope = _pubsub_envelope(
        {
            "records": [
                {"unique_id": "store_1", "ds": "2024-06-15", "y": 142.5},
                {"unique_id": "store_1", "ds": "2024-06-16", "y": 138.0},
            ]
        }
    )
    resp = client.post("/ingest/pubsub", json=envelope)
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "pubsub"
    assert data["flushed"] == 2

    # Verify data was written to parquet
    import pandas as pd

    df = pd.read_parquet(parquet_path)
    assert len(df) == 2
