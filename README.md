# Demand Forecasting MLOps System

A production-grade demand forecasting pipeline with automated training, champion/challenger evaluation, drift monitoring, prediction tracking, and model lifecycle management. Trains three model types (SeasonalNaive, AutoETS, MLP), promotes the best performer, and serves forecasts via a FastAPI endpoint.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           SYSTEM ARCHITECTURE                                │
│                                                                              │
│  External Systems (POS, IoT, ETL)                                            │
│       │ async, irregular                                                     │
│       ▼                                                                      │
│  ┌──────────┐     ┌─────────┐     ┌──────────┐     ┌──────────────┐         │
│  │ POST     │────▶│  Redis  │────▶│  Batch   │────▶│   Quality    │         │
│  │ /ingest  │     │  Buffer │flush│  Append  │     │   Gates      │         │
│  └──────────┘     └─────────┘     └──────────┘     └──────┬───────┘         │
│                    ▲  auto-flush                          │                  │
│                    │  (30s / 10 records)                   ▼                  │
│               ┌────┴─────┐              ┌──────────────────────────┐         │
│               │ Flush    │              │   Feature Engineering    │         │
│               │ Worker   │              │   (rolling, lags, cal)   │         │
│               └──────────┘              └────────────┬─────────────┘         │
│                                                      │                       │
│                                                      ▼                       │
│                                         ┌──────────────────────┐             │
│                                         │   Training Pipeline  │             │
│            ┌──────────────────────┐     │  SeasonalNaive       │             │
│            │    MLflow Server     │◀────│  AutoETS             │             │
│            │  metrics + artifacts │     │  MLP                 │             │
│            └──────────────────────┘     └──────────┬───────────┘             │
│                                                    │                         │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────▼──────────┐             │
│  │   Retrain    │◀──│    Drift     │   │ Evaluate & Promote   │             │
│  │   Trigger    │   │  Detection   │   │ (champion/challenger) │             │
│  └──────────────┘   └──────┬───────┘   └───────────┬──────────┘             │
│                            │            ┌──────────▼──────────┐              │
│                            │            │  Model Lifecycle    │              │
│                            │            │  (staging → prod)   │              │
│                            │            └──────────┬──────────┘              │
│  ┌──────────────┐   ┌──────▼───────┐   ┌──────────▼──────────┐              │
│  │  Prediction  │◀──│   FastAPI    │◀──│  Load Champion      │              │
│  │  Store (SQL) │   │   /predict   │   │  (or fallback)      │              │
│  └──────┬───────┘   └─────────────-┘   └─────────────────────┘              │
│         │                                                                    │
│  ┌──────▼───────┐   ┌──────────────┐                                        │
│  │ Join Actuals │──▶│  Accuracy    │                                        │
│  │ (log & join) │   │  History     │                                        │
│  └──────────────┘   └──────────────┘                                        │
│                                                                              │
│  ── Persistent Logs ──────────────────────────────────────────────────────── │
│  audit_log.jsonl │ drift_log.jsonl │ ingest_manifest.jsonl │ predictions.db  │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Quickstart

```bash
# 1. Install dependencies
make install

# 2. Start MLflow + Redis
make infra

# 3. Run full pipeline (data → quality → features → train → evaluate → promote → monitor)
make pipeline

# 4. Start the API
make serve

# 5. Get a forecast
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"store_id": "store_1"}'
```

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (for MLflow + Redis)
- `pip install -r requirements.txt`

For GCP deployment: Terraform, `gcloud` CLI, a GCP project with billing enabled.

---

## Launching the System

### Local Development

**Step 1: Infrastructure**

```bash
make infra          # Starts MLflow (port 5000) + Redis (port 6379)
```

MLflow UI is available at http://localhost:5000 once running.

**Step 2: Run the Pipeline**

```bash
make pipeline       # Full 7-step pipeline
```

This runs:
1. Generate synthetic sales data (5 stores × 365 days)
2. Data quality gates (schema, nulls, outliers, continuity)
3. Feature engineering (rolling averages, lags, calendar features)
4. Train all models (SeasonalNaive, AutoETS, MLP) — logged to MLflow
5. Evaluate and rank by WAPE — tag champion
6. Promote champion to production via lifecycle manager
7. Run drift detection (KS test on feature distributions)

**Step 3: Serve**

```bash
make serve          # FastAPI on port 8000
```

### Run Steps Individually

```bash
make data           # Generate synthetic data only
make features       # Compute features only
make train          # Train models only (requires MLflow)
make monitor        # One-shot drift check
```

### Tear Down

```bash
make infra-down     # Stop MLflow + Redis
make clean          # Remove all generated data, artifacts, models
```

---

## Debugging

### MLflow Won't Start

```bash
docker compose logs mlflow    # Check container logs
curl http://localhost:5000/health  # Should return "OK"
```

If volumes have permission issues, reset with:
```bash
docker compose down -v        # Removes named volumes
make infra                    # Recreate fresh
```

### Pipeline Fails at Training

Training requires MLflow to be running and healthy. Verify:
```bash
curl -s http://localhost:5000/health && echo " OK"
```

If you see connection refused, run `make infra` first and wait a few seconds for healthcheck to pass.

### API Returns Fallback Predictions

The API falls back to SeasonalNaive if:
- No champion model is found in `data/model_lifecycle.json`
- MLflow is unreachable (2s timeout on health check)
- The champion model's WAPE exceeded the 30% threshold during evaluation

Check the current model state:
```bash
curl http://localhost:8000/health
curl http://localhost:8000/model/info
```

### Tests Failing

```bash
make test           # Run all 48 tests

# Run a specific test file
python3 -m pytest tests/test_api.py -v

# Run with output visible
python3 -m pytest tests/test_backtest.py -v -s
```

Tests are self-contained — they monkeypatch config paths to temp directories and don't require MLflow or Docker running.

### Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PermissionError: '/mlflow'` | MLflow artifact path resolving locally | Ensure docker-compose.yml has `--serve-artifacts` and `--default-artifact-root mlflow-artifacts:/` |
| `ConnectionRefusedError` on port 5000 | MLflow not running | `make infra` and wait for healthcheck |
| `trainer_kwargs` TypeError | NeuralForecast 3.x API change | Pass `accelerator` and `enable_progress_bar` as direct kwargs to MLP, not inside `trainer_kwargs` |
| Drift detected on all features | Expected after fresh data generation | Train/test distribution shift is normal for synthetic data — not an error |

---

## Running Experiments

Experiments let you compare model configurations through controlled backtesting. Results are saved as JSON reports.

### Backtesting

Backtesting evaluates a model across multiple time splits to estimate real-world performance.

```bash
make backtest
```

Or programmatically:

```python
from src.backtest import run_backtest, BacktestConfig
import pandas as pd

df = pd.read_parquet("data/sales.parquet")

# Expanding window (all history → each test window)
config = BacktestConfig(horizon=7, n_splits=4, strategy="expanding")
result = run_backtest(df, "AutoETS", config=config)

# Sliding window (fixed 90-day window)
config = BacktestConfig(horizon=7, n_splits=4, strategy="sliding", window_size=90)
result = run_backtest(df, "MLP", config=config)

print(result["aggregate"])  # {mean_wape, mean_mae, mean_rmse}
print(result["per_split"])  # Metrics for each fold
```

**Strategies:**
- `expanding` — Training window grows with each split. Tests generalization as data accumulates.
- `sliding` — Fixed-size training window. Tests performance on recent data only.

The `gap` parameter adds days between train and test to simulate real-world latency (e.g., `gap=1` means you don't have yesterday's data yet).

### A/B Experiments

Compare multiple model configurations head-to-head:

```bash
make experiment
```

Or build a custom experiment:

```python
from src.experiment import run_experiment, ExperimentConfig
import pandas as pd

df = pd.read_parquet("data/sales.parquet")

config = ExperimentConfig(
    name="ets_vs_mlp_tuning",
    description="Compare AutoETS season lengths and MLP hidden sizes",
    model_configs=[
        {"model_type": "AutoETS", "params": {"season_length": 7}},
        {"model_type": "AutoETS", "params": {"season_length": 14}},
        {"model_type": "MLP", "params": {"hidden_size": 32, "max_steps": 100}},
        {"model_type": "MLP", "params": {"hidden_size": 128, "max_steps": 300}},
    ],
    backtest_config={"horizon": 7, "n_splits": 3, "strategy": "expanding"},
)

report = run_experiment(config, df)
print(f"Winner: {report['winner']} (WAPE: {report['winner_wape']})")
```

Reports are saved to `data/experiments/<experiment_id>.json` with full per-split metrics for reproducibility.

---

## Data Ingestion

The system supports two ingestion modes: **streaming** (for live data arriving asynchronously) and **batch** (for bulk loads).

### Streaming Ingestion

In a live system, sales data arrives asynchronously and irregularly — a POS terminal fires a sale event, an IoT sensor reports inventory, an ETL job pushes a batch of yesterday's numbers. The streaming pipeline handles this without blocking or data loss.

**How it works:**

```
POS / IoT / ETL                Forecast API               Background
     │                              │                        │
     │  POST /ingest/single         │                        │
     │  {store, date, sales}        │                        │
     │─────────────────────────────▶│                        │
     │                              │──▶ Validate record     │
     │                              │──▶ Push to Redis buf   │
     │  {"buffered": 1}             │                        │
     │◀─────────────────────────────│                        │
     │                              │                        │
     │  (more records arrive        │                        │
     │   over next 30 seconds...)   │                        │
     │                              │                        │
     │                              │    Flush worker fires  │
     │                              │    (30s interval OR    │
     │                              │     10+ records)       │
     │                              │                     ┌──┴──┐
     │                              │                     │Drain│
     │                              │                     │Redis│
     │                              │                     │Dedup│
     │                              │                     │Write│
     │                              │                     │.pqt │
     │                              │                     └──┬──┘
     │                              │  Sales data updated    │
     │                              │◀───────────────────────│
     │                              │  /predict uses new data│
```

Records go into a **Redis write buffer** (fast, concurrent-safe). A background worker inside the FastAPI process periodically flushes the buffer to the sales parquet via the existing `data_ingest.append_batch` — which handles deduplication on `(unique_id, ds)`.

**Sending data from an external system:**

```bash
# Single record (POS terminal, webhook, etc.)
curl -X POST http://localhost:8000/ingest/single \
  -H "Content-Type: application/json" \
  -d '{"unique_id": "store_1", "ds": "2025-01-15", "y": 142.5}'

# Batch of records (ETL job, nightly sync, etc.)
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "records": [
      {"unique_id": "store_1", "ds": "2025-01-15", "y": 142.5},
      {"unique_id": "store_1", "ds": "2025-01-16", "y": 138.0},
      {"unique_id": "store_2", "ds": "2025-01-15", "y": 201.3}
    ]
  }'
```

Both return immediately — the caller doesn't wait for the data to hit disk.

**Monitoring the buffer:**

```bash
# Check how many records are waiting
curl http://localhost:8000/ingest/buffer

# Force an immediate flush (don't wait for the timer)
curl -X POST http://localhost:8000/ingest/flush

# View ingestion history (all flushed batches)
curl http://localhost:8000/ingest/history
```

**Tuning the flush behavior:**

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `STREAM_FLUSH_INTERVAL` | `30` | Seconds between auto-flush checks |
| `STREAM_FLUSH_MIN_RECORDS` | `10` | Minimum buffered records to trigger auto-flush |
| `STREAM_MAX_BUFFER_SIZE` | `10000` | Safety cap on buffer size |
| `REDIS_HOST` | `localhost` | Redis connection host |
| `REDIS_PORT` | `6379` | Redis connection port |

For high-throughput scenarios (thousands of records/second), lower the flush interval and raise the min records threshold to batch more efficiently. For low-latency scenarios (need data reflected in predictions quickly), set `STREAM_FLUSH_MIN_RECORDS=1` and `STREAM_FLUSH_INTERVAL=5`.

**What happens if Redis goes down?** The `/ingest` endpoints return errors, but the rest of the API (`/predict`, `/health`, monitoring) continues working. The flush worker logs warnings and retries on the next interval. No data in the parquet is affected.

**Dead letter queue:** If a record can't be parsed during flush (malformed JSON, wrong types), it's moved to a Redis dead letter key (`forecast:ingest:dead_letter`) instead of being dropped silently.

### Batch Ingestion

For bulk loads (backfills, CSV imports, migration from another system), use the Python API directly:

```python
from src.data_ingest import append_batch
import pandas as pd

new_data = pd.DataFrame({
    "unique_id": ["store_1"] * 7,
    "ds": pd.date_range("2025-01-01", periods=7),
    "y": [150, 160, 145, 170, 155, 180, 165],
    "store_id": ["store_1"] * 7,
    "event_timestamp": pd.Timestamp.now(),
})

manifest = append_batch(new_data)
# {batch_id, timestamp, rows_added, total_rows, date_range}
```

### After Ingesting New Data

Whether data arrived via streaming or batch, the downstream steps are the same:

```bash
make features       # Recompute features (incremental-aware, skips unchanged rows)
make train          # Retrain models with new data
# Or run the full pipeline:
make pipeline
```

The `/predict` endpoint automatically picks up the latest data after a flush — the background worker reloads the sales DataFrame in memory.

---

## Monitoring & Model Lifecycle

### Drift Detection

```bash
make monitor              # One-shot drift check
make monitor-scheduled    # Persistent check + webhook alerting
```

The scheduler appends results to `data/drift_log.jsonl` and fires alerts to a configured webhook (Slack, PagerDuty, etc.). Set the webhook in `config/settings.py` or via environment variable:

```bash
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

### Retraining

```bash
make retrain
```

This checks two triggers:
- **Drift detected** — Recent drift log entries show feature distribution shift
- **Model staleness** — Current champion is older than `max_age_days` (default: 7)

If either triggers, it runs the full pipeline and promotes the new champion.

### Model Promotion & Rollback

Models move through stages: `staging → shadow → production → archived`

Promotion happens automatically in the pipeline, or manually:

```python
from src.model_lifecycle import promote, rollback, get_current_state

# Check current state
state = get_current_state()
print(state["production"])  # {run_id, model_name, promoted_at, reason}

# Manual promotion
promote("run_id_here", "AutoETS", "production", reason="manual override")

# Rollback to previous champion
rollback(reason="regression detected")
```

### Audit Trail

Every promotion, rollback, and retrain is logged to `data/audit_log.jsonl`:

```python
from src.audit import read_audit_log, get_feature_drift_timeline

# Recent actions
log = read_audit_log(limit=20, action_filter="promote")

# Drift history for a specific feature
timeline = get_feature_drift_timeline("rolling_sales_7d", limit=30)
```

---

## API Reference

### Forecast Service

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/predict` | Generate 7-day forecast for a store |
| `GET` | `/health` | Service health + current champion info |
| `GET` | `/model/info` | Detailed champion model metadata |

### Streaming Ingest

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/ingest` | Push a batch of sales records to the buffer |
| `POST` | `/ingest/single` | Push a single sales record to the buffer |
| `POST` | `/ingest/pubsub` | Receive Pub/Sub push messages (GCP mode) |
| `POST` | `/ingest/flush` | Manually trigger a buffer flush to parquet |
| `GET` | `/ingest/buffer` | Check buffer size and peek at queued records |
| `GET` | `/ingest/history` | View recent flush/ingestion batch history |

### Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/monitoring/actuals` | Submit actuals for a past prediction (log-and-join) |
| `GET` | `/monitoring/drift/history` | Recent drift detection results |
| `GET` | `/monitoring/drift/feature/{name}` | Drift p-value timeline for one feature |
| `GET` | `/monitoring/accuracy/history` | Accuracy metrics from joined predictions |
| `GET` | `/monitoring/audit` | Model lifecycle audit log |
| `GET` | `/monitoring/unjoined` | Predictions still awaiting actuals |

### Example: Full Prediction Lifecycle

```bash
# 1. Get a forecast
RESPONSE=$(curl -s -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"store_id": "store_1"}')

PREDICTION_ID=$(echo $RESPONSE | python3 -c "import sys,json; print(json.load(sys.stdin)['prediction_id'])")

# 2. Later, submit actual sales (log-and-join)
curl -X POST http://localhost:8000/monitoring/actuals \
  -H "Content-Type: application/json" \
  -d "{
    \"prediction_id\": \"$PREDICTION_ID\",
    \"actuals\": [
      {\"ds\": \"2024-10-01\", \"y\": 155},
      {\"ds\": \"2024-10-02\", \"y\": 162},
      {\"ds\": \"2024-10-03\", \"y\": 148}
    ]
  }"

# 3. Check accuracy over time
curl http://localhost:8000/monitoring/accuracy/history

# 4. Check for drift
curl http://localhost:8000/monitoring/drift/history

# 5. View audit trail
curl http://localhost:8000/monitoring/audit
```

---

## External Service Integration

### Consuming Forecasts

An external service (e.g., inventory management, supply chain optimizer) integrates by calling the `/predict` endpoint:

```
External Service                    Forecast API
      │                                  │
      │  POST /predict                   │
      │  {"store_id": "store_42"}        │
      │─────────────────────────────────▶│
      │                                  │──▶ Load champion model
      │                                  │──▶ Generate forecast
      │                                  │──▶ Log to prediction store
      │  {                               │
      │    "prediction_id": "uuid",      │
      │    "champion_model": "AutoETS",  │
      │    "forecast": [                 │
      │      {"ds": "2024-10-01",        │
      │       "value": 156.3},           │
      │      ...                         │
      │    ]                             │
      │  }                               │
      │◀─────────────────────────────────│
      │                                  │
      │  ... 7 days later ...            │
      │                                  │
      │  POST /monitoring/actuals        │
      │  {"prediction_id": "uuid",       │
      │   "actuals": [...]}              │
      │─────────────────────────────────▶│──▶ Compute WAPE/MAE
      │                                  │──▶ Store accuracy metrics
      │  {"wape": 0.08, "mae": 12.5}    │
      │◀─────────────────────────────────│
```

**Key integration points:**

1. **Forecast consumption** — `POST /predict` returns a `prediction_id` alongside the forecast. Store this ID to submit actuals later.

2. **Accuracy feedback loop** — After the forecast horizon passes (7 days), submit actual values via `POST /monitoring/actuals` with the saved `prediction_id`. The system computes WAPE and MAE, which feed into retrain decisions.

3. **Health monitoring** — Poll `GET /health` to verify the service is up and which model is active. If `fallback_active` is `true`, the system is using the SeasonalNaive heuristic instead of an ML model.

4. **Drift awareness** — Query `GET /monitoring/drift/history` to check if the model's input features are shifting. Sustained drift may indicate the model needs retraining or that upstream data pipelines have changed.

### Webhook Alerts

Configure `ALERT_WEBHOOK_URL` to receive drift and performance alerts in Slack, PagerDuty, or any webhook-compatible service. Alert payloads include:

```json
{
  "alert_type": "drift_detected",
  "timestamp": "2024-10-15T14:30:00",
  "payload": {
    "drifted_features": ["rolling_sales_7d", "lag_7"],
    "overall_drift": true
  }
}
```

### Feeding Live Data

An external system (POS, warehouse management, IoT sensors) pushes sales data as it happens:

```
POS Terminal / WMS / IoT           Forecast API
      │                                  │
      │  POST /ingest/single             │
      │  {"unique_id": "store_42",       │
      │   "ds": "2025-01-15",            │
      │   "y": 142.5}                    │
      │─────────────────────────────────▶│──▶ Validate
      │                                  │──▶ Push to Redis buffer
      │  {"buffered": 1,                 │
      │   "buffer_size": 47}             │    (returns immediately)
      │◀─────────────────────────────────│
      │                                  │
      │  (background worker auto-flushes │
      │   every 30s or 10+ records)      │
      │                                  │
      │  POST /predict                   │    (uses latest flushed data)
      │  {"store_id": "store_42"}        │
      │─────────────────────────────────▶│
      │  {"forecast": [...]}             │
      │◀─────────────────────────────────│
```

The caller doesn't wait for data to persist — the buffer absorbs bursts and irregular timing. For nightly ETL jobs that send larger payloads, use `POST /ingest` with multiple records in one request.

### Deploying Behind a Load Balancer

For production, deploy via GCP Cloud Run (see below) and point your services at the Cloud Run URL. The service is stateless — all state lives in SQLite files (`data/`) and MLflow. For multi-instance deployments, swap SQLite for PostgreSQL and local files for GCS.

---

## GCP Deployment

The `terraform/` directory provisions a single-region GCP environment: Cloud Run services, Cloud SQL (PostgreSQL), Pub/Sub for durable ingestion, VPC networking, GCS, Artifact Registry, and Cloud Monitoring alerts.

### Setup

```bash
# 1. Configure your project
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars: set project_id, region, environment, db_password, alert_email

# 2. Build and push the Docker image
make docker-build
make docker-push REGISTRY=<region>-docker.pkg.dev/<project>/<repo>

# 3. Deploy
make tf-init
make tf-plan        # Review what will be created
make tf-apply       # Deploy

# 4. Test
curl $(cd terraform && terraform output -raw api_url)/health

# 5. Publish sales data via Pub/Sub
gcloud pubsub topics publish $(cd terraform && terraform output -raw pubsub_ingest_topic) \
  --message '{"records": [{"unique_id": "store_1", "ds": "2025-01-15", "y": 142.5}]}'

# 6. Tear down when done
make tf-destroy
```

### What Gets Created

| Resource | Purpose | Cost (~monthly) |
|----------|---------|----------------|
| Cloud Run (forecast-api) | Serves `/predict` + `/ingest/pubsub` | Scale 0→1, ~$0 idle |
| Cloud Run (mlflow) | Experiment tracking + artifact proxy | Scale 0→1, ~$0 idle |
| Cloud SQL (PostgreSQL 15) | MLflow backend + prediction store | db-f1-micro ~$8 |
| Pub/Sub (ingest topic) | Durable streaming data ingestion | <$1 |
| Pub/Sub (dead letter topic) | Failed message inspection | <$1 |
| VPC + Connector | Private Cloud Run → Cloud SQL networking | ~$17 |
| GCS Bucket | Data, MLflow artifacts | 90-day lifecycle |
| Artifact Registry | Docker images | Pay per storage |
| Cloud Monitoring | Uptime checks, alerting (5xx, memory, downtime) | Free tier |
| Service Account | IAM for all service-to-service access | Free |

**Estimated incremental cost: ~$25-30/month.** Both Cloud Run services scale to zero when idle.

### Environment Variables for GCP

The Dockerfile and Cloud Run config set these automatically:

| Variable | Local Default | GCP Override |
|----------|--------------|-------------|
| `MLFLOW_TRACKING_URI` | `http://localhost:5000` | Cloud Run MLflow URL |
| `GCS_BUCKET` | `""` (local files) | GCS bucket name |
| `DATABASE_URL` | `""` (SQLite) | `postgresql://user:pass@private-ip:5432/predictions` |
| `PUBSUB_ENABLED` | `false` | `true` |
| `PUBSUB_TOPIC` | `""` | Pub/Sub topic ID |
| `ALERT_WEBHOOK_URL` | `""` (log only) | Slack/PagerDuty webhook |
| `REDIS_HOST` | `localhost` | Redis host (local mode only) |

### GCP Ingestion Flow

In GCP mode, data flows through Pub/Sub instead of Redis:

```
External System              Pub/Sub                  Cloud Run API
     │                          │                          │
     │  publish message         │                          │
     │  {"records": [...]}      │                          │
     │─────────────────────────▶│                          │
     │                          │  push to /ingest/pubsub  │
     │                          │─────────────────────────▶│
     │                          │                          │──▶ Decode envelope
     │                          │                          │──▶ Write to parquet
     │                          │           200 OK         │
     │                          │◀─────────────────────────│
     │                          │                          │
     │                     (on failure)                    │
     │                          │──▶ Dead letter topic     │
     │                          │    (retry / inspect)     │
```

Pub/Sub provides durable, at-least-once delivery with automatic retries and dead letter handling — no Redis needed in GCP.

---

## Infrastructure Roadmap

The current Terraform deploys a functional single-region environment. These features are not yet implemented but are scaffolded as TODO comments in the Terraform files:

### Security
- **API Gateway + JWT Auth** — Replace `allUsers` IAM with Cloud Endpoints or API Gateway for authenticated access (`cloud_run_api.tf`)
- **Cloud Armor** — WAF/DDoS protection policy in front of Cloud Run (`cloud_run_api.tf`)
- **Secret Manager** — Move `db_password` and other credentials out of Terraform variables into Secret Manager (`cloud_sql.tf`)

### Database
- **Cloud SQL HA** — Enable high availability with regional failover (`cloud_sql.tf`)
- **Read Replicas** — Add read replicas for MLflow query offloading (`cloud_sql.tf`)
- **Automated Backups** — Configure backup window and retention policy (`cloud_sql.tf`)
- **Cloud SQL Insights** — Enable query performance monitoring (`cloud_sql.tf`)

### Networking
- **Shared VPC** — For multi-project/team deployments (`vpc.tf`)
- **Cloud NAT** — For outbound internet access from private resources (`vpc.tf`)
- **Multi-region VPC Connectors** — Replicate connectors across regions (`vpc.tf`)

### Scaling & Multi-Region
- **Global HTTP(S) Load Balancer** — Route traffic to the nearest regional Cloud Run instance
- **Multi-region Cloud Run** — Deploy forecast API in multiple regions
- **Cloud SQL Cross-region Replicas** — Read replicas in secondary regions

### Data Pipeline
- **Cloud Scheduler** — Periodic retraining triggers via Pub/Sub (`pubsub.tf`)
- **Pub/Sub Schema Validation** — Enforce record schema at the topic level (`pubsub.tf`)
- **BigQuery Archival** — Archive ingested data to BigQuery for analytics (`pubsub.tf`)
- **Cloud Build CI/CD** — Automated build/deploy triggers on git push

### Monitoring
- **Custom WAPE Metrics** — Push model accuracy as Cloud Monitoring custom metrics (`monitoring.tf`)
- **Log-based Metrics** — Extract structured metrics from application logs (`monitoring.tf`)
- **Monitoring Dashboards** — Pre-built dashboards for API latency, error rates, model drift (`monitoring.tf`)

---

## Project Structure

```
forecasting-ml/
├── config/
│   └── settings.py              # Central configuration
├── service/
│   ├── app.py                   # FastAPI application + flush worker
│   ├── routes_ingest.py         # Streaming ingest endpoints
│   ├── routes_monitoring.py     # Monitoring endpoints
│   └── schemas.py               # Request/response models
├── src/
│   ├── train.py                 # Model training (3 model types)
│   ├── evaluate.py              # Champion/challenger ranking
│   ├── fallback.py              # SeasonalNaive heuristic
│   ├── backtest.py              # Time-series cross-validation
│   ├── experiment.py            # A/B experiment framework
│   ├── data_generator.py        # Synthetic data generation
│   ├── data_ingest.py           # Incremental batch ingestion
│   ├── stream_buffer.py         # Redis-backed streaming buffer
│   ├── data_quality.py          # Quality gates
│   ├── feature_engineering.py   # Feature computation
│   ├── feature_registry.py      # Declarative feature definitions
│   ├── monitor.py               # Drift detection (KS test)
│   ├── monitor_scheduler.py     # Scheduled monitoring + alerts
│   ├── model_lifecycle.py       # Promotion/rollback state machine
│   ├── retrain.py               # Retrain trigger logic
│   ├── prediction_store.py      # Prediction logging (SQLite/PostgreSQL)
│   └── audit.py                 # Audit log reader
├── scripts/
│   ├── run_pipeline.py          # 7-step orchestration
│   └── materialize_features.py  # Feast materialization
├── tests/                       # 57 tests across 15 files
├── terraform/                   # GCP infrastructure
├── feature_repo/                # Feast feature definitions
├── data/                        # Runtime data (gitignored)
├── Makefile                     # All operational targets
├── Dockerfile                   # Container image
├── docker-compose.yml           # Local infra (MLflow + Redis)
└── requirements.txt
```

## Makefile Reference

| Target | Description |
|--------|-------------|
| `make install` | Install Python dependencies |
| `make data` | Generate synthetic sales data |
| `make features` | Compute engineered features |
| `make train` | Train all models (requires MLflow) |
| `make serve` | Start FastAPI on port 8000 |
| `make test` | Run all 57 tests |
| `make pipeline` | Full end-to-end pipeline |
| `make infra` | Start MLflow + Redis |
| `make infra-down` | Stop infrastructure |
| `make backtest` | Run time-series cross-validation |
| `make experiment` | Run A/B model comparison |
| `make monitor` | One-shot drift check |
| `make monitor-scheduled` | Persistent drift check + alerting |
| `make retrain` | Check triggers and retrain if needed |
| `make docker-build` | Build Docker image |
| `make docker-push` | Push image to registry |
| `make deploy` | Build + push + terraform apply |
| `make tf-init/plan/apply/destroy` | Terraform lifecycle |
| `make clean` | Remove all generated data |
