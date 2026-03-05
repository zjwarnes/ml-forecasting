"""Request/response schemas for the forecast API."""

from pydantic import BaseModel
from datetime import datetime


class ForecastRequest(BaseModel):
    store_id: str


class ForecastResponse(BaseModel):
    store_id: str
    prediction_id: str
    champion_model: str
    fallback_active: bool
    forecast: list[dict]
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    champion_model: str | None
    fallback_active: bool


class ModelInfoResponse(BaseModel):
    champion_model: str
    champion_run_id: str | None
    metrics: dict
    fallback_active: bool
