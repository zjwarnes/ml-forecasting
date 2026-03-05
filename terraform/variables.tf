variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev/staging/prod)"
  type        = string
  default     = "dev"
}

variable "api_image" {
  description = "Docker image for the forecast API (set after building and pushing)"
  type        = string
  default     = ""
}

variable "mlflow_image" {
  description = "Docker image for MLflow server (must be in GCR, Artifact Registry, or Docker Hub — Cloud Run doesn't support ghcr.io)"
  type        = string
  default     = ""  # Empty = use Artifact Registry path (built from project/region)
}

# ── Cloud SQL ─────────────────────────────────────────────────────────

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_name_mlflow" {
  description = "Database name for MLflow tracking"
  type        = string
  default     = "mlflow"
}

variable "db_name_predictions" {
  description = "Database name for prediction store"
  type        = string
  default     = "predictions"
}

variable "db_user" {
  description = "Database user"
  type        = string
  default     = "forecast"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

# ── Monitoring ────────────────────────────────────────────────────────

variable "alert_email" {
  description = "Email for monitoring alert notifications (empty = no alerts)"
  type        = string
  default     = ""
}

# ── Pub/Sub ───────────────────────────────────────────────────────────

variable "pubsub_ack_deadline_seconds" {
  description = "Pub/Sub acknowledgment deadline in seconds"
  type        = number
  default     = 60
}

variable "pubsub_max_delivery_attempts" {
  description = "Max delivery attempts before dead-lettering"
  type        = number
  default     = 5
}
