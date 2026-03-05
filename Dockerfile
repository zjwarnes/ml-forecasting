FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# Install CPU-only PyTorch first to avoid downloading ~700MB CUDA/cuDNN
# (Cloud Run has no GPU — CUDA packages are wasted space and time)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Environment overrides for GCP deployment (defaults work for local)
ENV MLFLOW_TRACKING_URI="http://localhost:5000"
ENV GCS_BUCKET=""
ENV ALERT_WEBHOOK_URL=""
ENV DATABASE_URL=""
ENV PUBSUB_ENABLED="false"
ENV PUBSUB_TOPIC=""

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
