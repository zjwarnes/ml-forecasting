output "api_url" {
  description = "Forecast API URL"
  value       = google_cloud_run_v2_service.forecast_api.uri
}

output "mlflow_url" {
  description = "MLflow tracking server URL"
  value       = google_cloud_run_v2_service.mlflow.uri
}

output "gcs_bucket" {
  description = "GCS bucket for data and artifacts"
  value       = google_storage_bucket.forecast_bucket.name
}

output "artifact_registry" {
  description = "Docker image registry path"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.forecast_repo.repository_id}"
}

output "pubsub_ingest_topic" {
  description = "Pub/Sub topic for streaming sales data ingestion"
  value       = google_pubsub_topic.ingest.id
}

output "pubsub_dlq_topic" {
  description = "Pub/Sub dead letter topic for failed messages"
  value       = google_pubsub_topic.ingest_dead_letter.id
}

output "cloud_sql_instance" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.forecast_db.name
}

output "cloud_sql_private_ip" {
  description = "Cloud SQL private IP address"
  value       = google_sql_database_instance.forecast_db.private_ip_address
  sensitive   = true
}

output "cloud_sql_connection_name" {
  description = "Cloud SQL connection name (project:region:instance)"
  value       = google_sql_database_instance.forecast_db.connection_name
}

output "vpc_connector_name" {
  description = "Serverless VPC connector name"
  value       = google_vpc_access_connector.connector.name
}
