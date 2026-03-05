"""Redis-backed streaming buffer for async data ingestion.

Records arrive one-at-a-time or in small bursts via the API. They're pushed
into a Redis list (fast, concurrent-safe). A flush worker periodically drains
the buffer and appends to the sales parquet via data_ingest.append_batch.
"""

import json
import logging
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings

logger = logging.getLogger("stream_buffer")

REDIS_KEY = "forecast:ingest:buffer"
REDIS_DEAD_LETTER_KEY = "forecast:ingest:dead_letter"


def _get_redis():
    """Lazy Redis connection."""
    import redis
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True,
    )


def push_records(records: list[dict]) -> dict:
    """Push one or more sales records into the Redis buffer.

    Each record must have: unique_id, ds, y.
    Optional: store_id, event_timestamp.

    Returns: {buffered: int, buffer_size: int, timestamp: str}
    """
    r = _get_redis()
    pipe = r.pipeline()
    for rec in records:
        # Normalize timestamps to ISO strings
        if "ds" in rec and not isinstance(rec["ds"], str):
            rec["ds"] = str(rec["ds"])
        if "event_timestamp" not in rec:
            rec["event_timestamp"] = datetime.now().isoformat()
        rec["_buffered_at"] = datetime.now().isoformat()
        pipe.rpush(REDIS_KEY, json.dumps(rec))
    pipe.execute()

    buffer_size = r.llen(REDIS_KEY)
    logger.info(f"Buffered {len(records)} records (buffer size: {buffer_size})")

    return {
        "buffered": len(records),
        "buffer_size": buffer_size,
        "timestamp": datetime.now().isoformat(),
    }


def peek_buffer(limit: int = 10) -> dict:
    """Check buffer state without consuming records."""
    r = _get_redis()
    size = r.llen(REDIS_KEY)
    # Peek at first N records
    raw = r.lrange(REDIS_KEY, 0, limit - 1)
    samples = [json.loads(item) for item in raw]
    return {"buffer_size": size, "samples": samples}


def flush_buffer(min_records: int = 1) -> dict | None:
    """Drain the Redis buffer and append to sales parquet.

    Args:
        min_records: Minimum records required to trigger a flush.
            If buffer has fewer, returns None (no-op).

    Returns:
        Flush result dict or None if buffer too small.
    """
    r = _get_redis()
    buffer_size = r.llen(REDIS_KEY)

    if buffer_size < min_records:
        return None

    # Drain all records atomically using a pipeline
    pipe = r.pipeline()
    pipe.lrange(REDIS_KEY, 0, -1)
    pipe.delete(REDIS_KEY)
    results = pipe.execute()
    raw_records = results[0]

    if not raw_records:
        return None

    records = []
    failed = []
    for raw in raw_records:
        try:
            rec = json.loads(raw)
            rec.pop("_buffered_at", None)
            records.append(rec)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Skipping malformed record: {e}")
            failed.append(raw)

    # Send failed records to dead letter queue
    if failed:
        pipe = r.pipeline()
        for f in failed:
            pipe.rpush(REDIS_DEAD_LETTER_KEY, f)
        pipe.execute()
        logger.warning(f"Moved {len(failed)} malformed records to dead letter queue")

    if not records:
        return {"flushed": 0, "failed": len(failed), "timestamp": datetime.now().isoformat()}

    # Convert to DataFrame and append via data_ingest
    df = pd.DataFrame(records)
    df["ds"] = pd.to_datetime(df["ds"])
    if "y" in df.columns:
        df["y"] = pd.to_numeric(df["y"], errors="coerce")
    if "event_timestamp" in df.columns:
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

    from src.data_ingest import append_batch
    batch_id = f"stream_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    manifest = append_batch(df, existing_path=settings.SALES_PARQUET, batch_id=batch_id)

    result = {
        "flushed": len(records),
        "failed": len(failed),
        "batch_id": batch_id,
        "manifest": manifest,
        "timestamp": datetime.now().isoformat(),
    }
    logger.info(f"Flushed {len(records)} records as batch '{batch_id}'")
    return result


def get_dead_letters(limit: int = 50) -> list[str]:
    """Retrieve records that failed to parse during flush."""
    r = _get_redis()
    return r.lrange(REDIS_DEAD_LETTER_KEY, 0, limit - 1)


def buffer_size() -> int:
    """Current number of records waiting in the buffer."""
    r = _get_redis()
    return r.llen(REDIS_KEY)
