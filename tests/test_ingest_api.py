"""Tests for the /ingest API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from datetime import datetime


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
            return items[start:end + 1]

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
                        results.append(items[cmd[2]:])
                    else:
                        results.append(items[cmd[2]:end + 1])
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


def test_ingest_single_record(client):
    resp = client.post("/ingest/single", json={
        "unique_id": "store_1",
        "ds": "2024-06-15",
        "y": 142.5,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["buffered"] == 1


def test_ingest_batch(client):
    resp = client.post("/ingest", json={
        "records": [
            {"unique_id": "store_1", "ds": "2024-06-15", "y": 142.5},
            {"unique_id": "store_1", "ds": "2024-06-16", "y": 138.0},
            {"unique_id": "store_2", "ds": "2024-06-15", "y": 200.0},
        ]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["buffered"] == 3


def test_ingest_empty_batch(client):
    resp = client.post("/ingest", json={"records": []})
    assert resp.status_code == 400


def test_buffer_status(client):
    # Push something first
    client.post("/ingest/single", json={
        "unique_id": "store_1", "ds": "2024-06-15", "y": 100,
    })
    resp = client.get("/ingest/buffer")
    assert resp.status_code == 200
    data = resp.json()
    assert data["buffer_size"] >= 1
