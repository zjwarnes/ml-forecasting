"""Tests for monitoring API routes."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    from src.data_generator import generate_sales_data
    from config.settings import SALES_PARQUET

    if not SALES_PARQUET.exists():
        generate_sales_data()

    from fastapi.testclient import TestClient
    from service.app import app
    with TestClient(app) as c:
        yield c


def test_drift_history(client):
    resp = client.get("/monitoring/drift/history")
    assert resp.status_code == 200
    assert "records" in resp.json()


def test_accuracy_history(client):
    resp = client.get("/monitoring/accuracy/history")
    assert resp.status_code == 200
    assert "records" in resp.json()


def test_audit_log(client):
    resp = client.get("/monitoring/audit")
    assert resp.status_code == 200
    assert "records" in resp.json()


def test_submit_actuals_not_found(client):
    resp = client.post("/monitoring/actuals", json={
        "prediction_id": "nonexistent",
        "actuals": [{"ds": "2024-01-01", "y": 100}],
    })
    assert resp.status_code == 404
