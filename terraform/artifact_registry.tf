resource "google_artifact_registry_repository" "forecast_repo" {
  location      = var.region
  repository_id = "forecast-ml-${var.environment}"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}
