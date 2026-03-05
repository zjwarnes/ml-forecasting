resource "google_service_account" "forecast_sa" {
  account_id   = "forecast-ml-${var.environment}"
  display_name = "Forecast ML Service Account"

  depends_on = [google_project_service.apis]
}

# GCS access for data and artifacts
resource "google_storage_bucket_iam_member" "sa_gcs" {
  bucket = google_storage_bucket.forecast_bucket.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.forecast_sa.email}"
}

# Artifact Registry reader (pull images)
resource "google_artifact_registry_repository_iam_member" "sa_ar" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.forecast_repo.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.forecast_sa.email}"
}

# Cloud SQL client (private IP connection)
resource "google_project_iam_member" "sa_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.forecast_sa.email}"
}

# Pub/Sub subscriber (receive push messages)
resource "google_project_iam_member" "sa_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.forecast_sa.email}"
}

# Pub/Sub publisher (publish to topics)
resource "google_project_iam_member" "sa_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.forecast_sa.email}"
}

# Cloud Monitoring metric writer
resource "google_project_iam_member" "sa_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.forecast_sa.email}"
}
