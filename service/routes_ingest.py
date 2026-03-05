"""API routes for streaming data ingestion."""

import base64
import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings

router = APIRouter(prefix="/ingest", tags=["ingest"])


class SalesRecord(BaseModel):
    unique_id: str
    ds: str
    y: float
    store_id: str | None = None
    event_timestamp: str | None = None


class IngestRequest(BaseModel):
    records: list[SalesRecord]


class IngestSingleRequest(BaseModel):
    unique_id: str
    ds: str
    y: float
    store_id: str | None = None


@router.post("")
def ingest_records(request: IngestRequest):
    """Push one or more sales records into the streaming buffer.

    Records are buffered in Redis and periodically flushed to the
    sales parquet. This endpoint returns immediately — it does not
    wait for the flush.
    """
    if not request.records:
        raise HTTPException(status_code=400, detail="No records provided.")

    from src.stream_buffer import push_records
    records = [r.model_dump() for r in request.records]

    # Populate store_id from unique_id if not provided
    for rec in records:
        if not rec.get("store_id"):
            rec["store_id"] = rec["unique_id"]

    result = push_records(records)
    return result


@router.post("/single")
def ingest_single(request: IngestSingleRequest):
    """Push a single sales record into the streaming buffer.

    Convenience endpoint for systems that send one record at a time.
    """
    from src.stream_buffer import push_records
    rec = request.model_dump()
    if not rec.get("store_id"):
        rec["store_id"] = rec["unique_id"]

    result = push_records([rec])
    return result


@router.post("/pubsub")
async def ingest_pubsub(request: Request):
    """Receive a Pub/Sub push message containing sales records.

    Pub/Sub pushes an envelope: {"message": {"data": "<base64>"}, "subscription": "..."}.
    The base64-decoded data should be a JSON object with a "records" list,
    each record having {unique_id, ds, y, store_id?}.

    In GCP mode (no Redis), writes directly via append_batch() since
    Pub/Sub already handles durability and retry.
    """
    try:
        envelope = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body.")

    message = envelope.get("message")
    if not message or "data" not in message:
        raise HTTPException(status_code=400, detail="Missing message.data in Pub/Sub envelope.")

    try:
        payload_bytes = base64.b64decode(message["data"])
        payload = json.loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 or JSON in message.data.")

    records = payload.get("records", [])
    if not records:
        # Single-record format: the payload itself is the record
        if "unique_id" in payload and "ds" in payload and "y" in payload:
            records = [payload]
        else:
            raise HTTPException(status_code=400, detail="No records found in payload.")

    # Populate store_id from unique_id if missing
    for rec in records:
        if not rec.get("store_id"):
            rec["store_id"] = rec.get("unique_id", "unknown")

    # In GCP mode (Pub/Sub enabled), write directly — no Redis buffer needed
    if settings.PUBSUB_ENABLED:
        import pandas as pd
        from src.data_ingest import append_batch

        df = pd.DataFrame(records)
        df["ds"] = pd.to_datetime(df["ds"])
        df["y"] = pd.to_numeric(df["y"], errors="coerce")
        if "event_timestamp" not in df.columns:
            df["event_timestamp"] = pd.Timestamp.now()
        else:
            df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

        result = append_batch(df, existing_path=settings.SALES_PARQUET)
        return {"source": "pubsub", "flushed": len(df), "result": result}

    # Local mode: push through Redis buffer like other endpoints
    from src.stream_buffer import push_records
    result = push_records(records)
    return {"source": "pubsub", "buffered": result.get("buffered", 0), "result": result}


@router.post("/flush")
def flush_buffer():
    """Manually trigger a buffer flush to the sales parquet.

    Drains all buffered records from Redis, deduplicates, and appends
    to the sales parquet file. Returns the flush result.
    """
    from src.stream_buffer import flush_buffer as do_flush
    result = do_flush(min_records=1)
    if result is None:
        return {"message": "Buffer empty, nothing to flush.", "flushed": 0}
    return result


@router.get("/buffer")
def buffer_status():
    """Check the current state of the ingest buffer."""
    from src.stream_buffer import peek_buffer
    return peek_buffer(limit=5)


@router.get("/history")
def ingest_history(limit: int = 20):
    """Return recent ingestion batch history."""
    from src.data_ingest import get_ingest_history
    return {"records": get_ingest_history(limit)}
