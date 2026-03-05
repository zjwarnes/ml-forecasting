# --------------------------------------------------------------------------
# Cloud SQL PostgreSQL
# --------------------------------------------------------------------------
# Single instance hosting both the MLflow tracking backend and the
# prediction store. Private IP only — reached via VPC connector.
#
# TODO: Enable automated backups with point-in-time recovery for production
# TODO: Move db_password to Secret Manager (google_secret_manager_secret)
# TODO: Add Cloud SQL read replicas for production read scaling
# TODO: Add Cloud SQL Insights for query performance monitoring
# TODO: Switch to db-custom-1-3840 or higher for production workloads

resource "google_sql_database_instance" "forecast_db" {
  name             = "forecast-db-${var.environment}"
  database_version = "POSTGRES_15"
  region           = var.region

  deletion_protection = false # Easy teardown for dev/test

  settings {
    tier              = var.db_tier
    availability_type = "ZONAL"  # No HA for cost control
    disk_size         = 10       # GB minimum
    disk_type         = "PD_HDD" # HDD for cost savings (use PD_SSD in prod)
    disk_autoresize   = false    # Fixed size for cost predictability

    ip_configuration {
      ipv4_enabled    = false # No public IP
      private_network = google_compute_network.forecast_vpc.id
    }

    database_flags {
      name  = "max_connections"
      value = "50"
    }

    # TODO: Enable for production
    # backup_configuration {
    #   enabled                        = true
    #   point_in_time_recovery_enabled = true
    #   start_time                     = "03:00"
    # }
  }

  depends_on = [
    google_service_networking_connection.private_vpc_connection,
    google_project_service.apis,
  ]
}

resource "google_sql_database" "mlflow" {
  name     = var.db_name_mlflow
  instance = google_sql_database_instance.forecast_db.name
}

resource "google_sql_database" "predictions" {
  name     = var.db_name_predictions
  instance = google_sql_database_instance.forecast_db.name
}

resource "google_sql_user" "forecast_user" {
  name     = var.db_user
  instance = google_sql_database_instance.forecast_db.name
  password = var.db_password
}
