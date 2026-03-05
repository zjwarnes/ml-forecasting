.PHONY: install data features train serve test pipeline infra clean \
       backtest experiment monitor-scheduled retrain promote rollback \
       tf-init tf-plan tf-apply tf-destroy docker-build docker-push deploy

# ── Local Development ────────────────────────────────────────────────

# Install all dependencies
install:
	pip install -r requirements.txt

# Generate synthetic sales data
data:
	python3 -m src.data_generator

# Compute engineered features
features:
	python3 -m src.feature_engineering

# Train all models (requires MLflow server running)
train:
	python3 -m src.train

# Start the FastAPI serving endpoint
serve:
	uvicorn service.app:app --host 0.0.0.0 --port 8000 --reload

# Run test suite
test:
	python3 -m pytest tests/ -v --timeout=30

# Run full pipeline: data -> quality -> features -> train -> evaluate -> promote -> monitor
pipeline:
	python3 scripts/run_pipeline.py

# ── Infrastructure ───────────────────────────────────────────────────

# Start local infrastructure (MLflow + Redis)
infra:
	docker compose up -d

# Stop local infrastructure
infra-down:
	docker compose down

# ── Feast ────────────────────────────────────────────────────────────

feast-apply:
	cd feature_repo && feast apply

feast-materialize:
	python3 scripts/materialize_features.py

# ── Backtesting & Experiments ────────────────────────────────────────

backtest:
	python3 -m src.backtest

experiment:
	python3 -m src.experiment

# ── Monitoring & Lifecycle ───────────────────────────────────────────

# One-shot drift check
monitor:
	python3 -m src.monitor

# Scheduled monitoring (appends to drift log, fires alerts)
monitor-scheduled:
	python3 -m src.monitor_scheduler

# Check if retrain is needed and trigger if so
retrain:
	python3 -m src.retrain

# ── GCP Deployment ───────────────────────────────────────────────────

tf-init:
	cd terraform && terraform init

tf-plan:
	cd terraform && terraform plan

tf-apply:
	cd terraform && terraform apply

tf-destroy:
	cd terraform && terraform destroy

docker-build:
	docker build -t forecast-api:latest .

# Usage: make docker-push REGISTRY=<region>-docker.pkg.dev/<project>/<repo>
docker-push:
	docker tag forecast-api:latest $(REGISTRY)/forecast-api:latest
	docker push $(REGISTRY)/forecast-api:latest

deploy: docker-build docker-push tf-apply

# ── Cleanup ──────────────────────────────────────────────────────────

clean:
	rm -rf data/sales.parquet data/features.parquet data/predictions.db
	rm -rf data/audit_log.jsonl data/drift_log.jsonl data/ingest_manifest.jsonl
	rm -rf data/model_lifecycle.json data/experiments/
	rm -rf mlruns/ mlartifacts/ autoets_model/
	rm -rf feature_repo/data/registry.db feature_repo/data/online.db

# Full setup from scratch
all: install data features infra train
