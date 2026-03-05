resource "google_cloud_run_v2_service" "forecast_api" {
  name     = "forecast-api-${var.environment}"
  location = var.region

  template {
    vpc_access {
      connector = google_vpc_access_connector.connector.id
      egress    = "PRIVATE_RANGES_ONLY"
    }

    scaling {
      min_instance_count = 0 # Scale to zero when idle
      max_instance_count = 1 # Single instance for cost control
    }

    containers {
      image = var.api_image != "" ? var.api_image : "${var.region}-docker.pkg.dev/${var.project_id}/forecast-ml-${var.environment}/forecast-api:latest"

      ports { container_port = 8000 }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "MLFLOW_TRACKING_URI"
        value = google_cloud_run_v2_service.mlflow.uri
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.forecast_bucket.name
      }
      env {
        name  = "DATABASE_URL"
        value = "postgresql://${var.db_user}:${var.db_password}@${google_sql_database_instance.forecast_db.private_ip_address}:5432/${var.db_name_predictions}"
      }
      env {
        name  = "PUBSUB_TOPIC"
        value = google_pubsub_topic.ingest.id
      }
      env {
        name  = "PUBSUB_ENABLED"
        value = "true"
      }
    }

    service_account = google_service_account.forecast_sa.email
  }

  depends_on = [
    google_project_service.apis,
    google_sql_database.predictions,
  ]
}

# Allow unauthenticated access (for testing — lock down in production)
# TODO: Replace with API Gateway + JWT auth for production
# TODO: Add Cloud Armor security policy for WAF/DDoS protection
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.forecast_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
