# --------------------------------------------------------------------------
# Cloud Monitoring: Uptime checks + alert policies
# --------------------------------------------------------------------------
# Basic observability: is the API up, are requests failing, is memory tight.
# All alerts are conditional on alert_email being set.
#
# TODO: Add Cloud Armor WAF/DDoS protection (google_compute_security_policy)
# TODO: Add custom metrics for prediction accuracy (WAPE) via monitoring API
# TODO: Add log-based metrics for application errors (google_logging_metric)
# TODO: Add monitoring dashboard (google_monitoring_dashboard)
# TODO: Add PagerDuty/Slack notification channels for production

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "Forecast ML Alerts - ${var.environment}"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }
}

# Uptime check: GET /health every 5 minutes
resource "google_monitoring_uptime_check_config" "api_health" {
  display_name = "forecast-api-health-${var.environment}"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path           = "/health"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"

    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = replace(google_cloud_run_v2_service.forecast_api.uri, "https://", "")
    }
  }
}

# Alert: API is down (uptime check failing)
resource "google_monitoring_alert_policy" "api_uptime" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "Forecast API Down - ${var.environment}"
  combiner     = "OR"

  conditions {
    display_name = "Uptime check failure"

    condition_threshold {
      filter          = "resource.type = \"uptime_url\" AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id = \"${google_monitoring_uptime_check_config.api_health.uptime_check_id}\""
      duration        = "300s"
      comparison      = "COMPARISON_LT"
      threshold_value = 1

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.project_id"]
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "1800s"
  }
}

# Alert: 5xx error rate exceeds threshold
resource "google_monitoring_alert_policy" "api_error_rate" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "Forecast API Error Rate - ${var.environment}"
  combiner     = "OR"

  conditions {
    display_name = "5xx error rate exceeds 5%"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${google_cloud_run_v2_service.forecast_api.name}\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_RATE"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "1800s"
  }
}

# Alert: Memory utilization exceeds 80%
resource "google_monitoring_alert_policy" "memory_utilization" {
  count        = var.alert_email != "" ? 1 : 0
  display_name = "Forecast API Memory High - ${var.environment}"
  combiner     = "OR"

  conditions {
    display_name = "Memory utilization exceeds 80%"

    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${google_cloud_run_v2_service.forecast_api.name}\" AND metric.type = \"run.googleapis.com/container/memory/utilizations\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "1800s"
  }
}
