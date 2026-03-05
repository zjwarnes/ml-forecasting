"""Tests for the FastAPI forecast service."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client():
    """Create a test client, generating data if needed."""
    from src.data_generator import generate_sales_data
    from config.settings import SALES_PARQUET

    if not SALES_PARQUET.exists():
        generate_sales_data()

    from fastapi.testclient import TestClient
    from service.app import app
    with TestClient(app) as c:
        yield c


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_predict_valid_store(client):
    resp = client.post("/predict", json={"store_id": "store_1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["store_id"] == "store_1"
    assert len(data["forecast"]) == 7
    assert "prediction_id" in data


def test_predict_unknown_store(client):
    resp = client.post("/predict", json={"store_id": "nonexistent"})
    assert resp.status_code == 404


def test_model_info(client):
    resp = client.get("/model/info")
    assert resp.status_code == 200
    assert "champion_model" in resp.json()
