import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
FEATURE_REPO = PROJECT_ROOT / "feature_repo"
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
MLFLOW_ARTIFACT_ROOT = str(PROJECT_ROOT / "mlruns")
GCS_BUCKET = os.getenv("GCS_BUCKET", "")  # empty = local mode

# ── Data Generation ────────────────────────────────────────────────────
STORES = [f"store_{i}" for i in range(1, 6)]  # 5 stores
DATA_START = "2024-01-01"
DATA_END = "2024-12-31"
SALES_PARQUET = DATA_DIR / "sales.parquet"
FEATURES_PARQUET = DATA_DIR / "features.parquet"

# ── Model Config ───────────────────────────────────────────────────────
FORECAST_HORIZON = 7       # predict 7 days ahead
SEASON_LENGTH = 7          # weekly seasonality
INPUT_SIZE = 28            # 4 weeks of history for neural models
TRAIN_CUTOFF = "2024-10-01"  # first 9 months train, last 3 validate

# MLP (neuralforecast)
MLP_CONFIG = {
    "h": FORECAST_HORIZON,
    "input_size": INPUT_SIZE,
    "hidden_size": 64,
    "max_steps": 200,
    "accelerator": "cpu",
}

# ── Evaluation Thresholds ──────────────────────────────────────────────
WAPE_THRESHOLD = 0.30      # 30% — if best model exceeds this, use fallback
RMSE_ALERT_THRESHOLD = 50  # absolute RMSE trigger for alerting

# ── MLflow ─────────────────────────────────────────────────────────────
EXPERIMENT_NAME = "demand_forecast"
MODEL_REGISTRY_NAME = "demand_forecast_champion"

# ── Serving ────────────────────────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000

# ── Monitoring ─────────────────────────────────────────────────────────
DRIFT_THRESHOLD = 0.05     # p-value threshold for drift detection
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")  # optional Slack/PagerDuty webhook
MONITORING_SCHEDULE_HOURS = 24

# ── Redis / Streaming ─────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
STREAM_FLUSH_INTERVAL_SECONDS = int(os.getenv("STREAM_FLUSH_INTERVAL", "30"))
STREAM_FLUSH_MIN_RECORDS = int(os.getenv("STREAM_FLUSH_MIN_RECORDS", "10"))
STREAM_MAX_BUFFER_SIZE = int(os.getenv("STREAM_MAX_BUFFER_SIZE", "10000"))

# ── Database (PostgreSQL for GCP, SQLite for local) ──────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "")  # empty = SQLite, set = PostgreSQL

# ── Pub/Sub (GCP streaming ingestion) ────────────────────────────────
PUBSUB_ENABLED = os.getenv("PUBSUB_ENABLED", "false").lower() == "true"
PUBSUB_TOPIC = os.getenv("PUBSUB_TOPIC", "")

# ── Persistence (logs, audit, predictions) ─────────────────────────────
INGEST_MANIFEST = DATA_DIR / "ingest_manifest.jsonl"
AUDIT_LOG = DATA_DIR / "audit_log.jsonl"
DRIFT_LOG = DATA_DIR / "drift_log.jsonl"
PREDICTIONS_DB = DATA_DIR / "predictions.db"
LIFECYCLE_DB = DATA_DIR / "model_lifecycle.json"
EXPERIMENTS_DIR = DATA_DIR / "experiments"
