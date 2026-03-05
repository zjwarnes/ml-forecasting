"""Tests for the streaming ingest buffer."""

import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime


@pytest.fixture
def mock_redis():
    """Mock Redis client with list-like behavior."""
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

    with patch("src.stream_buffer._get_redis", return_value=FakeRedis()):
        storage.clear()
        yield storage


def test_push_records(mock_redis):
    from src.stream_buffer import push_records, buffer_size

    result = push_records([
        {"unique_id": "store_1", "ds": "2024-06-01", "y": 100},
        {"unique_id": "store_1", "ds": "2024-06-02", "y": 110},
    ])

    assert result["buffered"] == 2
    assert result["buffer_size"] == 2
    assert buffer_size() == 2


def test_push_and_flush(mock_redis, tmp_path, monkeypatch):
    import config.settings as settings
    monkeypatch.setattr(settings, "SALES_PARQUET", tmp_path / "sales.parquet")
    monkeypatch.setattr(settings, "INGEST_MANIFEST", tmp_path / "manifest.jsonl")

    from src.stream_buffer import push_records, flush_buffer, buffer_size

    push_records([
        {"unique_id": "store_1", "ds": "2024-06-01", "y": 100, "store_id": "store_1"},
        {"unique_id": "store_1", "ds": "2024-06-02", "y": 110, "store_id": "store_1"},
        {"unique_id": "store_2", "ds": "2024-06-01", "y": 200, "store_id": "store_2"},
    ])

    result = flush_buffer(min_records=1)

    assert result is not None
    assert result["flushed"] == 3
    assert result["failed"] == 0
    assert buffer_size() == 0

    # Verify parquet was written
    import pandas as pd
    df = pd.read_parquet(tmp_path / "sales.parquet")
    assert len(df) == 3


def test_flush_empty_buffer(mock_redis):
    from src.stream_buffer import flush_buffer
    result = flush_buffer(min_records=1)
    assert result is None


def test_flush_respects_min_records(mock_redis):
    from src.stream_buffer import push_records, flush_buffer

    push_records([{"unique_id": "store_1", "ds": "2024-06-01", "y": 100}])
    result = flush_buffer(min_records=5)
    assert result is None  # Only 1 record, need 5


def test_peek_buffer(mock_redis):
    from src.stream_buffer import push_records, peek_buffer

    push_records([
        {"unique_id": "store_1", "ds": "2024-06-01", "y": 100},
        {"unique_id": "store_2", "ds": "2024-06-01", "y": 200},
    ])

    result = peek_buffer(limit=1)
    assert result["buffer_size"] == 2
    assert len(result["samples"]) == 1
