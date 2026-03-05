# GCP Deployment & Validation Guide

Step-by-step guide for deploying the forecasting system to Google Cloud Platform and validating that every component works correctly.

---

## Prerequisites

Before starting, ensure you have:

- [ ] **GCP project** with billing enabled
- [ ] **gcloud CLI** installed and authenticated (`gcloud auth login`)
- [ ] **Terraform >= 1.5** installed
- [ ] **Docker** installed and running
- [ ] **Project owner or editor IAM role** on the GCP project (needed for API enablement and IAM bindings)

```bash
# Verify tools
gcloud version
terraform version
docker info

# Set your project
gcloud config set project YOUR_PROJECT_ID
```

---

## Phase 1: Configure Variables

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
project_id  = "your-gcp-project-id"   # GCP project ID
region      = "us-central1"            # Any GCP region with Cloud Run + Cloud SQL
environment = "dev"                    # dev / staging / prod
db_password = "a-strong-password-here" # Cloud SQL password (move to Secret Manager for prod)
alert_email = "your-email@example.com" # Monitoring alerts (leave empty to skip alerts)
```

**Validate:** Ensure the project exists and you have access.

```bash
gcloud projects describe YOUR_PROJECT_ID --format="value(projectId)"
```

---

## Phase 2: Initialize & Plan Terraform

```bash
cd terraform

terraform init
terraform plan
```

> **Auth errors?** If you see `invalid_grant` or `invalid_rapt` errors, your application-default credentials have expired. Fix with:
> ```bash
> gcloud auth application-default login
> ```
> Then retry `terraform plan`.

**What to look for in the plan output:**

| Expected Resource | Count |
|---|---|
| `google_project_service.apis` | 10 APIs enabled |
| `google_compute_network` + `subnetwork` | 1 VPC + 1 subnet |
| `google_compute_global_address` + `service_networking_connection` | Private Services Access |
| `google_vpc_access_connector` | 1 connector (2-3 instances) |
| `google_sql_database_instance` | 1 PostgreSQL 15 instance |
| `google_sql_database` | 2 databases (mlflow, predictions) |
| `google_sql_user` | 1 database user |
| `google_cloud_run_v2_service` | 2 services (forecast-api, mlflow) |
| `google_storage_bucket` | 1 GCS bucket |
| `google_artifact_registry_repository` | 1 Docker registry |
| `google_pubsub_topic` | 2 topics (ingest, dead letter) |
| `google_pubsub_subscription` | 2 subscriptions (push, DLQ pull) |
| `google_service_account` | 1 service account + 6 IAM bindings |
| `google_monitoring_uptime_check_config` | 1 uptime check |
| `google_monitoring_alert_policy` | 3 alert policies (if alert_email set) |

Total: approximately **30-35 resources** depending on whether alerts are enabled.

**Red flags to watch for:**
- `Error: Missing required provider` → Run `terraform init` first
- `Permission denied` → Ensure you have Owner/Editor on the project
- IP range conflicts → The plan uses `10.0.0.0/24` (subnet) and `10.8.0.0/28` (VPC connector). If these conflict with existing VPCs, adjust `vpc.tf`

---

## Phase 3: Build & Push Docker Images

Both the forecast API and MLflow images must be in Artifact Registry before `terraform apply` creates the Cloud Run services. Cloud Run only supports images from GCR, Artifact Registry, or Docker Hub — it cannot pull from `ghcr.io` or other third-party registries.

```bash
# From project root
cd /path/to/forecasting-ml

# Authenticate Docker to Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev

# Apply terraform first to create the registry (run from terraform/)
cd terraform
terraform apply -target=google_artifact_registry_repository.forecast_repo -target=google_project_service.apis

# Get the registry path
REGISTRY=$(terraform output -raw artifact_registry)
cd ..

# Build and push the forecast API image
# (uses CPU-only PyTorch to avoid downloading ~700MB of CUDA/cuDNN packages)
docker build -t forecast-api:latest .
docker tag forecast-api:latest $REGISTRY/forecast-api:latest
docker push $REGISTRY/forecast-api:latest

# Build and push the custom MLflow image (includes psycopg2 for PostgreSQL)
docker build -f Dockerfile.mlflow -t mlflow:v2.16.2 .
docker tag mlflow:v2.16.2 $REGISTRY/mlflow:v2.16.2
docker push $REGISTRY/mlflow:v2.16.2
```

> **Why a custom MLflow image?** The upstream `ghcr.io/mlflow/mlflow` image does not include `psycopg2`, which is required for the PostgreSQL backend store. `Dockerfile.mlflow` extends the official image with `psycopg2-binary`.

**Validate:** Confirm both images are in the registry.

```bash
gcloud artifacts docker images list $REGISTRY --format="table(package,version)"
```

You should see both `forecast-api` and `mlflow` listed.

---

## Phase 4: Deploy Infrastructure

```bash
cd terraform
terraform apply
```

This takes **5-10 minutes**, primarily due to Cloud SQL instance creation and VPC peering.

Save the outputs — you'll need them for validation:

```bash
terraform output
```

Expected outputs:

```
api_url               = "https://forecast-api-dev-XXXXXX-uc.a.run.app"
mlflow_url            = "https://mlflow-dev-XXXXXX-uc.a.run.app"
gcs_bucket            = "forecast-ml-dev-XXXXXX"
artifact_registry     = "us-central1-docker.pkg.dev/PROJECT/forecast-ml-dev"
pubsub_ingest_topic   = "projects/PROJECT/topics/forecast-ingest-dev"
pubsub_dlq_topic      = "projects/PROJECT/topics/forecast-ingest-dlq-dev"
cloud_sql_instance    = "forecast-db-dev"
cloud_sql_connection_name = "PROJECT:us-central1:forecast-db-dev"
vpc_connector_name    = "forecast-vpc-cx-dev"
```

---

## Phase 5: Validate Each Component

Work through these checks in order. Each section builds on the previous one.

### 5.1 — API Health

```bash
API_URL=$(cd terraform && terraform output -raw api_url)

curl -s $API_URL/health | python3 -m json.tool
```

**Expected response:**

```json
{
    "status": "ok",
    "champion_model": null,
    "fallback_active": true
}
```

- `status: "ok"` → Cloud Run is running, the container started
- `champion_model: null` → Expected on first deploy (no pipeline has run yet)
- `fallback_active: true` → Forecasts will use SeasonalNaive heuristic

**If this fails:**
- `502/503` → Container is still starting. Wait 30 seconds, retry
- `Connection refused` → Check Cloud Run logs: `gcloud run services logs read forecast-api-dev --region=us-central1`
- `403 Forbidden` → IAM `allUsers` binding may not have applied. Check `gcloud run services get-iam-policy forecast-api-dev --region=us-central1`

### 5.2 — MLflow Tracking Server

```bash
MLFLOW_URL=$(cd terraform && terraform output -raw mlflow_url)

curl -s $MLFLOW_URL/health
```

**Expected:** Returns `OK` (plain text).

Then verify the UI is accessible by opening `$MLFLOW_URL` in a browser. You should see the MLflow experiment tracking interface.

**Validate PostgreSQL backend:**

```bash
# MLflow should have created its tables in the mlflow database
gcloud sql connect forecast-db-dev --database=mlflow --user=forecast --quiet
# At the psql prompt:
\dt
# You should see mlflow system tables (experiments, runs, metrics, params, etc.)
\q
```

> Note: `gcloud sql connect` requires the Cloud SQL Auth Proxy. If it's not available, this check can be done after deploying a Cloud SQL Proxy sidecar or via the GCP Console → SQL → Connect.

**If MLflow returns 503:**
- Check container logs: `gcloud run services logs read mlflow-dev --region=us-central1`
- **Memory exhaustion**: The default MLflow gunicorn config spawns 4 workers. With SQLAlchemy + psycopg2, this exceeds 512Mi and causes an OOM restart loop. The terraform config uses `--workers 1` and `1Gi` memory to prevent this. If you see clean startup logs followed by 503 on first request, increase memory or reduce workers.
- **Missing `psycopg2`**: If logs show `No module named 'psycopg2'`, the wrong image was pushed. Rebuild from `Dockerfile.mlflow` and verify locally: `docker run --rm IMAGE python -c "import psycopg2; print(psycopg2.__version__)"`
- **VPC connector not ready**: The connector needs ~2 minutes after creation. Verify state: `gcloud compute networks vpc-access connectors describe forecast-vpc-cx-dev --region=us-central1`

### 5.3 — Cloud SQL Connectivity

```bash
# Verify the instance exists and is running
gcloud sql instances describe forecast-db-dev --format="table(state,ipAddresses)"
```

**Expected:** State = `RUNNABLE`, and you should see a `PRIVATE` IP address (no public IP).

```bash
# Verify both databases exist
gcloud sql databases list --instance=forecast-db-dev --format="table(name)"
```

**Expected output:**

```
NAME
mlflow
predictions
postgres
```

(The `postgres` database is created by default.)

### 5.4 — VPC & Private Networking

```bash
# VPC exists
gcloud compute networks describe forecast-vpc-dev --format="table(name,subnetworks)"

# Connector is active
gcloud compute networks vpc-access connectors describe forecast-vpc-cx-dev \
  --region=us-central1 \
  --format="table(state,minInstances,maxInstances)"
```

**Expected:** Connector state = `READY`, min=2, max=3.

**Verify Cloud Run can reach Cloud SQL** (indirect check):

```bash
# If the API health check passed (5.1), the container started successfully.
# The container environment has DATABASE_URL set to the private IP.
# If Cloud SQL were unreachable, the prediction_store would fail silently
# (it creates tables on first connection).

# Force a prediction store write by hitting /predict:
curl -s -X POST $API_URL/predict \
  -H "Content-Type: application/json" \
  -d '{"store_id": "store_1"}' | python3 -m json.tool
```

This will return a 503 ("No sales data loaded") on a fresh deploy, which is expected — but the prediction store connection is tested during the attempt. Check logs for database errors:

```bash
gcloud run services logs read forecast-api-dev --region=us-central1 --limit=20
```

No `psycopg2` or connection errors = Cloud SQL connectivity is working.

### 5.5 — GCS Bucket

```bash
GCS_BUCKET=$(cd terraform && terraform output -raw gcs_bucket)

# Bucket exists
gsutil ls gs://$GCS_BUCKET/

# Test write access (from service account perspective)
echo "test" | gsutil cp - gs://$GCS_BUCKET/test.txt
gsutil rm gs://$GCS_BUCKET/test.txt
```

**Verify lifecycle policy:**

```bash
gsutil lifecycle get gs://$GCS_BUCKET/
```

Should show a 90-day delete rule.

### 5.6 — Pub/Sub Ingestion Pipeline

This is the most important validation — it tests the full data flow from an external publisher through to the API.

**Step 1: Publish a test message**

```bash
TOPIC=$(cd terraform && terraform output -raw pubsub_ingest_topic)

gcloud pubsub topics publish $TOPIC \
  --message '{"records": [{"unique_id": "store_1", "ds": "2025-01-15", "y": 142.5}]}'
```

**Step 2: Check that the push subscription delivered to the API**

```bash
# Wait 5-10 seconds for Pub/Sub to push to Cloud Run
sleep 10

# Check API logs for the ingest
gcloud run services logs read forecast-api-dev --region=us-central1 --limit=10
```

Look for a log line indicating the `/ingest/pubsub` endpoint was hit. You should see either:
- A successful ingest message (200 response)
- Or an error if data storage isn't configured yet (which still proves the pipeline works)

**Step 3: Verify the push subscription is healthy**

```bash
gcloud pubsub subscriptions describe forecast-ingest-push-dev \
  --format="table(pushConfig.pushEndpoint,deadLetterPolicy.deadLetterTopic,ackDeadlineSeconds)"
```

**Expected:**
- `pushEndpoint` = `https://forecast-api-dev-XXXX-uc.a.run.app/ingest/pubsub`
- `deadLetterTopic` = `projects/PROJECT/topics/forecast-ingest-dlq-dev`
- `ackDeadlineSeconds` = `60`

**Step 4: Verify dead letter queue**

```bash
# Publish an invalid message to test DLQ routing
gcloud pubsub topics publish $TOPIC --message 'not-valid-json-{{'

# After the max delivery attempts (5), the message should land in the DLQ
# This takes a few minutes due to retry backoff (10s-300s)

# Check for messages in DLQ (non-destructive peek)
gcloud pubsub subscriptions pull forecast-ingest-dlq-pull-dev --limit=5 --auto-ack
```

### 5.7 — Cloud Monitoring

```bash
# Uptime check is configured
gcloud monitoring uptime list-configs --format="table(displayName,httpCheck.path,period)"
```

**Expected:** `forecast-api-health-dev` checking `/health` every `300s`.

**Verify alerts (if alert_email was set):**

```bash
gcloud alpha monitoring policies list --format="table(displayName,enabled)"
```

**Expected 3 policies:**
- `Forecast API Down - dev`
- `Forecast API Error Rate - dev`
- `Forecast API Memory High - dev`

**Check your email** for a verification notification from Google Cloud Monitoring (you may need to confirm the notification channel).

### 5.8 — IAM & Service Account

```bash
SA_EMAIL="forecast-ml-dev@YOUR_PROJECT_ID.iam.gserviceaccount.com"

gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:$SA_EMAIL" \
  --format="table(bindings.role)"
```

**Expected roles:**
- `roles/cloudsql.client`
- `roles/monitoring.metricWriter`
- `roles/pubsub.publisher`
- `roles/pubsub.subscriber`

Additionally, bucket-level and AR-level bindings:
```bash
gsutil iam get gs://$GCS_BUCKET/ | grep forecast-ml
```

Should show `roles/storage.objectAdmin`.

---

## Phase 6: End-to-End Smoke Test

Once all components are validated individually, run the full data flow:

```bash
API_URL=$(cd terraform && terraform output -raw api_url)
TOPIC=$(cd terraform && terraform output -raw pubsub_ingest_topic)

# 1. Health check
echo "=== Health ==="
curl -s $API_URL/health | python3 -m json.tool

# 2. Publish sales data via Pub/Sub
echo "=== Publishing test data ==="
gcloud pubsub topics publish $TOPIC --message '{
  "records": [
    {"unique_id": "store_1", "ds": "2025-01-15", "y": 142.5},
    {"unique_id": "store_1", "ds": "2025-01-16", "y": 138.0},
    {"unique_id": "store_1", "ds": "2025-01-17", "y": 155.0},
    {"unique_id": "store_2", "ds": "2025-01-15", "y": 200.0}
  ]
}'

# 3. Wait for push delivery
sleep 15

# 4. Check API logs
echo "=== Recent logs ==="
gcloud run services logs read forecast-api-dev --region=us-central1 --limit=5

# 5. Try a prediction (will fail with 503 on fresh deploy since no pipeline has run,
#    but this validates the API is processing requests)
echo "=== Predict ==="
curl -s -X POST $API_URL/predict \
  -H "Content-Type: application/json" \
  -d '{"store_id": "store_1"}' | python3 -m json.tool

# 6. Check MLflow UI
echo "=== MLflow ==="
MLFLOW_URL=$(cd terraform && terraform output -raw mlflow_url)
curl -s -o /dev/null -w "MLflow HTTP status: %{http_code}\n" $MLFLOW_URL/health

# 7. Check monitoring
echo "=== Uptime checks ==="
gcloud monitoring uptime list-configs --format="table(displayName,httpCheck.path)"
```

### Expected Results Summary

| Check | Expected Result |
|---|---|
| `/health` | `{"status": "ok", "champion_model": null, "fallback_active": true}` |
| Pub/Sub publish | `messageIds: ["XXXX"]` |
| API logs after publish | `/ingest/pubsub` request logged |
| `/predict` | `503` (no sales data) or `200` (if data was ingested) |
| MLflow `/health` | HTTP 200 |
| Uptime check | Listed and active |

---

## Phase 7: Running the Pipeline in GCP

To get the system fully operational (with trained models and real predictions), you'll need to run the pipeline against the deployed infrastructure. This can be done from your local machine pointing at the GCP services:

```bash
# Point your local environment at GCP
export MLFLOW_TRACKING_URI=$(cd terraform && terraform output -raw mlflow_url)
export GCS_BUCKET=$(cd terraform && terraform output -raw gcs_bucket)

# Run the pipeline locally (trains models, logs to GCP MLflow)
make pipeline

# The /predict endpoint will now serve real model predictions
curl -s -X POST $API_URL/predict \
  -H "Content-Type: application/json" \
  -d '{"store_id": "store_1"}' | python3 -m json.tool
```

After the pipeline runs, re-check health:

```bash
curl -s $API_URL/health | python3 -m json.tool
```

You should now see `champion_model` populated and `fallback_active: false`.

---

## Teardown

```bash
cd terraform
terraform destroy
```

This destroys all resources. Cloud SQL `deletion_protection` is set to `false` for dev, so it will be deleted without manual intervention.

**Verify cleanup:**

```bash
# No lingering resources
gcloud run services list --region=us-central1 --filter="metadata.name~forecast"
gcloud sql instances list --filter="name~forecast"
gcloud pubsub topics list --filter="name~forecast"
gcloud compute networks list --filter="name~forecast"
```

All should return empty results.

---

## Troubleshooting Reference

| Symptom | Likely Cause | Fix |
|---|---|---|
| `terraform plan` returns `invalid_grant` / `invalid_rapt` | Application-default credentials expired | Run `gcloud auth application-default login` |
| `terraform apply` hangs on Cloud SQL | VPC peering setup is slow | Wait 5-10 min; check `gcloud services peered-dns-domains list` |
| Cloud Run rejects image from `ghcr.io` | Cloud Run only supports GCR, Artifact Registry, Docker Hub | Build and push to Artifact Registry instead |
| Docker build times out downloading CUDA/cuDNN (~700MB) | PyTorch defaults to GPU build with nvidia packages | Install CPU-only PyTorch first: `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| MLflow returns `503`, logs show clean startup | 4 gunicorn workers OOM in 512Mi | Increase memory to 1Gi and add `--workers 1` to args |
| MLflow fails with `No module named 'psycopg2'` | Base MLflow image lacks PostgreSQL driver | Build from `Dockerfile.mlflow`; verify: `docker run --rm IMAGE python -c "import psycopg2"` |
| Cloud Run returns `502` | Container crash on startup | Check logs: `gcloud run services logs read SERVICE --region=REGION` |
| MLflow can't connect to Cloud SQL | VPC connector not ready | Wait 2 min after creation; verify state: `gcloud compute networks vpc-access connectors describe CONNECTOR --region=REGION` |
| Pub/Sub messages going to DLQ | API returning non-2xx to push | Check API logs for error on `/ingest/pubsub` |
| No monitoring alerts | `alert_email` not set | Set `alert_email` in `terraform.tfvars` and re-apply |
| `403` on Cloud Run URL | IAM binding not applied | Re-run `terraform apply`; check `gcloud run services get-iam-policy` |
| Cloud SQL `SUSPENDED` | Free tier billing issue | Check billing; restart: `gcloud sql instances restart INSTANCE` |
| Docker push fails | Not authenticated to AR | Run `gcloud auth configure-docker REGION-docker.pkg.dev` |
| VPC connector `ERROR` state | IP range conflict | Check for overlapping ranges in existing VPCs; adjust `ip_cidr_range` in `vpc.tf` |

---

## Cost Monitoring

After deployment, monitor costs in the GCP Console under **Billing → Reports**. Filter by labels or service:

| Service | Expected Monthly Cost |
|---|---|
| Cloud SQL (db-f1-micro) | ~$8 |
| VPC Connector (2 instances) | ~$17 |
| Cloud Run (scale to zero) | ~$0 idle, usage-based |
| Pub/Sub | <$1 for low volume |
| GCS | <$1 for small data |
| Monitoring | Free tier |
| **Total (idle)** | **~$25-30** |

Set a **billing alert** at $50/month to catch unexpected usage:

```bash
# Or configure in GCP Console → Billing → Budgets & alerts
gcloud billing budgets create \
  --billing-account=BILLING_ACCOUNT_ID \
  --display-name="Forecast ML Budget" \
  --budget-amount=50 \
  --threshold-rule=percent=0.8 \
  --threshold-rule=percent=1.0
```
