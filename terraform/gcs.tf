resource "google_storage_bucket" "forecast_bucket" {
  name          = "${var.project_id}-forecast-${var.environment}"
  location      = var.region
  force_destroy = true # Clean teardown for testing

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 90 }
    action { type = "Delete" }
  }

  depends_on = [google_project_service.apis]
}
