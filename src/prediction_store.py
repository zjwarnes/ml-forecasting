"""Prediction store: log predictions, join actuals, compute accuracy.

Supports SQLite (local dev) and PostgreSQL (GCP deployment).
Backend selected by DATABASE_URL env var: empty = SQLite, set = PostgreSQL.
"""

import sqlite3
import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config.settings as settings

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS predictions (
        prediction_id TEXT PRIMARY KEY,
        store_id TEXT NOT NULL,
        model_name TEXT NOT NULL,
        forecast_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        actuals_json TEXT,
        joined_at TEXT,
        wape REAL,
        mae REAL
    )
"""


def _use_postgres() -> bool:
    return bool(settings.DATABASE_URL)


def _get_conn(db_path: Path | None = None):
    """Get a database connection. Returns (conn, placeholder) tuple.

    placeholder is '?' for SQLite and '%s' for PostgreSQL.
    """
    if _use_postgres():
        import psycopg2
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(_CREATE_TABLE)
        conn.commit()
        return conn
    else:
        path = db_path or settings.PREDICTIONS_DB
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute(_CREATE_TABLE)
        conn.commit()
        return conn


def _ph(sql: str) -> str:
    """Translate ? placeholders to %s for PostgreSQL."""
    if _use_postgres():
        return sql.replace("?", "%s")
    return sql


def _execute(conn, sql: str, params=None):
    """Execute SQL with placeholder translation."""
    translated = _ph(sql)
    if _use_postgres():
        cur = conn.cursor()
        cur.execute(translated, params)
        return cur
    else:
        if params:
            return conn.execute(translated, params)
        return conn.execute(translated)


def _upsert_sql() -> str:
    """Get the upsert SQL for the current backend."""
    if _use_postgres():
        return "INSERT INTO predictions (prediction_id, store_id, model_name, forecast_json, created_at) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (prediction_id) DO UPDATE SET store_id=EXCLUDED.store_id, model_name=EXCLUDED.model_name, forecast_json=EXCLUDED.forecast_json, created_at=EXCLUDED.created_at"
    return "INSERT OR REPLACE INTO predictions (prediction_id, store_id, model_name, forecast_json, created_at) VALUES (?,?,?,?,?)"


def log_prediction(
    prediction_id: str,
    store_id: str,
    model_name: str,
    forecast: list[dict],
    db_path: Path | None = None,
):
    """Log a prediction for later accuracy tracking."""
    conn = _get_conn(db_path)
    sql = _upsert_sql()
    if _use_postgres():
        cur = conn.cursor()
        cur.execute(sql, (prediction_id, store_id, model_name, json.dumps(forecast, default=str), datetime.now().isoformat()))
    else:
        conn.execute(sql, (prediction_id, store_id, model_name, json.dumps(forecast, default=str), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def join_actuals(
    prediction_id: str,
    actuals: list[dict],
    db_path: Path | None = None,
) -> dict | None:
    """Join actual values with a past prediction, computing accuracy metrics."""
    conn = _get_conn(db_path)
    cur = _execute(conn, "SELECT forecast_json FROM predictions WHERE prediction_id = ?", (prediction_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    forecast = json.loads(row[0])
    forecast_by_ds = {str(f["ds"])[:10]: f.get("SeasonalNaive", f.get("y", 0)) for f in forecast}
    actuals_by_ds = {str(a["ds"])[:10]: a["y"] for a in actuals}

    matched_forecast = []
    matched_actuals = []
    for ds in forecast_by_ds:
        if ds in actuals_by_ds:
            matched_forecast.append(forecast_by_ds[ds])
            matched_actuals.append(actuals_by_ds[ds])

    if matched_actuals:
        actual_arr = np.array(matched_actuals)
        pred_arr = np.array(matched_forecast)
        mae = float(np.mean(np.abs(actual_arr - pred_arr)))
        wape = float(np.sum(np.abs(actual_arr - pred_arr)) / np.sum(np.abs(actual_arr))) if np.sum(np.abs(actual_arr)) > 0 else None
    else:
        mae, wape = None, None

    _execute(
        conn,
        "UPDATE predictions SET actuals_json=?, joined_at=?, wape=?, mae=? WHERE prediction_id=?",
        (json.dumps(actuals, default=str), datetime.now().isoformat(), wape, mae, prediction_id),
    )
    conn.commit()
    conn.close()

    return {"prediction_id": prediction_id, "wape": wape, "mae": mae, "matched_days": len(matched_actuals)}


def get_unjoined_predictions(older_than_days: int = 7, db_path: Path | None = None) -> list[dict]:
    """Find predictions that should have actuals by now but don't."""
    conn = _get_conn(db_path)
    cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
    cur = _execute(
        conn,
        "SELECT prediction_id, store_id, model_name, created_at FROM predictions WHERE actuals_json IS NULL AND created_at < ?",
        (cutoff,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"prediction_id": r[0], "store_id": r[1], "model_name": r[2], "created_at": r[3]} for r in rows]


def get_accuracy_history(limit: int = 50, db_path: Path | None = None) -> list[dict]:
    """Get recent predictions that have been joined with actuals."""
    conn = _get_conn(db_path)
    cur = _execute(
        conn,
        "SELECT prediction_id, store_id, model_name, wape, mae, joined_at FROM predictions WHERE actuals_json IS NOT NULL ORDER BY joined_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    conn.close()
    return [{"prediction_id": r[0], "store_id": r[1], "model_name": r[2], "wape": r[3], "mae": r[4], "joined_at": r[5]} for r in rows]
