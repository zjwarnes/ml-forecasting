resource "google_cloud_run_v2_service" "mlflow" {
  name     = "mlflow-${var.environment}"
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
      image = var.mlflow_image != "" ? var.mlflow_image : "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.forecast_repo.repository_id}/mlflow:v2.16.2"

      ports { container_port = 5000 }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      # PostgreSQL backend (persistent) + GCS artifacts
      # Single worker to fit in memory; Cloud Run handles concurrency via instances
      args = [
        "mlflow", "server",
        "--host", "0.0.0.0",
        "--port", "5000",
        "--workers", "1",
        "--backend-store-uri", "postgresql://${var.db_user}:${var.db_password}@${google_sql_database_instance.forecast_db.private_ip_address}:5432/${var.db_name_mlflow}",
        "--default-artifact-root", "gs://${google_storage_bucket.forecast_bucket.name}/mlartifacts",
      ]
    }

    service_account = google_service_account.forecast_sa.email
  }

  depends_on = [
    google_project_service.apis,
    google_sql_database.mlflow,
  ]
}

# Allow unauthenticated access (for testing — lock down in production)
# TODO: Restrict to internal traffic only or require auth
resource "google_cloud_run_v2_service_iam_member" "mlflow_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mlflow.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
