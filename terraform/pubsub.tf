# --------------------------------------------------------------------------
# Pub/Sub: Streaming ingestion pipeline
# --------------------------------------------------------------------------
# Replaces the Redis buffer for GCP deployments. Cloud Run is stateless,
# so an in-memory Redis buffer would be lost on scale-down. Pub/Sub
# provides durable, at-least-once delivery with automatic retries.
#
# Flow: External system → publish to topic → push subscription →
#       POST /ingest/pubsub on Cloud Run → append to data store
#
# TODO: Add Cloud Scheduler to publish periodic retraining triggers
# TODO: Add google_pubsub_schema for message format validation
# TODO: Add BigQuery subscription for raw event archival

data "google_project" "project" {
  project_id = var.project_id
}

# Dead letter topic (created first — main subscription references it)
resource "google_pubsub_topic" "ingest_dead_letter" {
  name = "forecast-ingest-dlq-${var.environment}"

  depends_on = [google_project_service.apis]
}

# Main ingestion topic
resource "google_pubsub_topic" "ingest" {
  name = "forecast-ingest-${var.environment}"

  message_retention_duration = "86400s" # 24h retention for replay

  depends_on = [google_project_service.apis]
}

# Push subscription → Cloud Run /ingest/pubsub endpoint
resource "google_pubsub_subscription" "ingest_push" {
  name  = "forecast-ingest-push-${var.environment}"
  topic = google_pubsub_topic.ingest.id

  ack_deadline_seconds = var.pubsub_ack_deadline_seconds

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.forecast_api.uri}/ingest/pubsub"

    oidc_token {
      service_account_email = google_service_account.forecast_sa.email
      audience              = google_cloud_run_v2_service.forecast_api.uri
    }
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.ingest_dead_letter.id
    max_delivery_attempts = var.pubsub_max_delivery_attempts
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }

  depends_on = [google_project_service.apis]
}

# Pull subscription on DLQ for manual inspection / reprocessing
resource "google_pubsub_subscription" "ingest_dlq_pull" {
  name  = "forecast-ingest-dlq-pull-${var.environment}"
  topic = google_pubsub_topic.ingest_dead_letter.id

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s" # 7 days

  depends_on = [google_project_service.apis]
}

# Pub/Sub service agent needs publisher rights on DLQ for dead-letter forwarding
resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  topic  = google_pubsub_topic.ingest_dead_letter.id
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dlq_subscriber" {
  subscription = google_pubsub_subscription.ingest_push.id
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.project.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}
