"""FastAPI forecast service with champion model serving and heuristic fallback."""

import asyncio
import uuid
import logging
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import (
    SALES_PARQUET, FORECAST_HORIZON, SEASON_LENGTH,
    MLFLOW_TRACKING_URI, API_HOST, API_PORT,
)
from service.schemas import (
    ForecastRequest, ForecastResponse, HealthResponse, ModelInfoResponse,
)
from src.fallback import seasonal_naive_forecast
from service.routes_monitoring import router as monitoring_router
from service.routes_ingest import router as ingest_router

logger = logging.getLogger("forecast_service")

# ── State loaded at startup ────────────────────────────────────────────
_state = {
    "champion_model": None,
    "champion_run_id": None,
    "metrics": {},
    "fallback_active": True,  # start in fallback mode until a model is loaded
    "sales_df": None,
}


def load_state():
    """Load latest sales data and champion model info.

    Checks model_lifecycle.json first (authoritative), then falls back to MLflow.
    """
    # Try lifecycle file first
    from config.settings import LIFECYCLE_DB
    try:
        if LIFECYCLE_DB.exists():
            import json
            state = json.loads(LIFECYCLE_DB.read_text())
            prod = state.get("production")
            if prod:
                _state["champion_model"] = prod.get("model_name")
                _state["champion_run_id"] = prod.get("run_id")
                _state["fallback_active"] = _state["champion_model"] == "SeasonalNaive"
                logger.info(f"Loaded champion from lifecycle: {_state['champion_model']}")
    except Exception as e:
        logger.warning(f"Could not read lifecycle DB: {e}")

    if SALES_PARQUET.exists():
        _state["sales_df"] = pd.read_parquet(SALES_PARQUET)
        logger.info(f"Loaded sales data: {len(_state['sales_df'])} rows")

    try:
        import mlflow
        import requests
        # Quick check if MLflow server is reachable before attempting queries
        requests.get(MLFLOW_TRACKING_URI + "/health", timeout=2)
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        client = mlflow.tracking.MlflowClient()

        experiment = client.get_experiment_by_name("demand_forecast")
        if experiment:
            runs = client.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string="tags.model_status = 'champion'",
                order_by=["start_time DESC"],
                max_results=1,
            )
            if runs:
                run = runs[0]
                _state["champion_model"] = run.data.tags.get("model_name", "unknown")
                _state["champion_run_id"] = run.info.run_id
                _state["metrics"] = {k: v for k, v in run.data.metrics.items()}
                _state["fallback_active"] = _state["champion_model"] == "SeasonalNaive"
                logger.info(f"Champion model: {_state['champion_model']}")
    except Exception as e:
        logger.warning(f"MLflow unavailable ({e}). Using fallback mode.")
        _state["fallback_active"] = True


async def _flush_worker():
    """Background task: periodically flush the Redis ingest buffer to parquet."""
    import config.settings as settings
    interval = getattr(settings, "STREAM_FLUSH_INTERVAL_SECONDS", 30)
    min_records = getattr(settings, "STREAM_FLUSH_MIN_RECORDS", 10)
    logger.info(f"Flush worker started (interval={interval}s, min_records={min_records})")

    while True:
        await asyncio.sleep(interval)
        try:
            from src.stream_buffer import flush_buffer
            result = flush_buffer(min_records=min_records)
            if result and result.get("flushed", 0) > 0:
                logger.info(f"Auto-flush: {result['flushed']} records flushed")
                # Reload sales data so /predict uses latest data
                if SALES_PARQUET.exists():
                    _state["sales_df"] = pd.read_parquet(SALES_PARQUET)
        except Exception as e:
            logger.warning(f"Flush worker error: {e}")


@asynccontextmanager
async def lifespan(app):
    load_state()

    # Start background flush worker if Redis is available
    flush_task = None
    try:
        from src.stream_buffer import buffer_size
        buffer_size()  # test Redis connection
        flush_task = asyncio.create_task(_flush_worker())
        logger.info("Streaming ingest enabled (Redis connected)")
    except Exception:
        logger.info("Streaming ingest disabled (Redis unavailable)")

    yield

    if flush_task:
        flush_task.cancel()
        try:
            await flush_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Demand Forecast Service", version="1.0.0", lifespan=lifespan)
app.include_router(monitoring_router)
app.include_router(ingest_router)


@app.post("/predict", response_model=ForecastResponse)
def predict(request: ForecastRequest):
    """Generate forecast for a store. Falls back to SeasonalNaive on any error."""
    prediction_id = str(uuid.uuid4())

    if _state["sales_df"] is None:
        raise HTTPException(status_code=503, detail="No sales data loaded. Run the pipeline first.")

    store_data = _state["sales_df"][_state["sales_df"]["unique_id"] == request.store_id]
    if len(store_data) == 0:
        raise HTTPException(status_code=404, detail=f"Store '{request.store_id}' not found.")

    # Always use fallback for now (model serving will be added with MLflow model loading)
    # In production, this would try the champion model first, catch errors, then fallback
    try:
        forecast_df = seasonal_naive_forecast(
            store_data[["unique_id", "ds", "y"]],
            horizon=FORECAST_HORIZON,
            season_length=SEASON_LENGTH,
        )
        forecast_records = forecast_df.to_dict(orient="records")
        # Convert Timestamps to strings for JSON serialization
        for rec in forecast_records:
            rec["ds"] = str(rec["ds"])

    except Exception as e:
        logger.error(f"Forecast failed for {request.store_id}: {e}")
        raise HTTPException(status_code=500, detail="Forecast generation failed.")

    # Log prediction for later accuracy tracking (log-and-join)
    try:
        from src.prediction_store import log_prediction
        log_prediction(prediction_id, request.store_id,
                       _state.get("champion_model") or "SeasonalNaive", forecast_records)
    except Exception as e:
        logger.warning(f"Failed to log prediction: {e}")

    return ForecastResponse(
        store_id=request.store_id,
        prediction_id=prediction_id,
        champion_model=_state.get("champion_model") or "SeasonalNaive",
        fallback_active=_state["fallback_active"],
        forecast=forecast_records,
        timestamp=datetime.now().isoformat(),
    )


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        champion_model=_state.get("champion_model"),
        fallback_active=_state["fallback_active"],
    )


@app.get("/model/info", response_model=ModelInfoResponse)
def model_info():
    return ModelInfoResponse(
        champion_model=_state.get("champion_model") or "SeasonalNaive",
        champion_run_id=_state.get("champion_run_id"),
        metrics=_state.get("metrics", {}),
        fallback_active=_state["fallback_active"],
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("service.app:app", host=API_HOST, port=API_PORT, reload=True)
