# --------------------------------------------------------------------------
# VPC + Serverless VPC Connector
# --------------------------------------------------------------------------
# Cloud Run services need private access to Cloud SQL. A custom VPC with
# Private Services Access and a Serverless VPC Connector enables this.
#
# TODO: Shared VPC for multi-project setups
# TODO: Cloud NAT for controlled outbound traffic
# TODO: For multi-region, replicate VPC connector per region

resource "google_compute_network" "forecast_vpc" {
  name                    = "forecast-vpc-${var.environment}"
  auto_create_subnetworks = false

  depends_on = [google_project_service.apis]
}

resource "google_compute_subnetwork" "forecast_subnet" {
  name          = "forecast-subnet-${var.environment}"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.forecast_vpc.id
}

# Reserved IP range for Private Services Access (Cloud SQL peering)
resource "google_compute_global_address" "private_ip_range" {
  name          = "forecast-private-ip-${var.environment}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.forecast_vpc.id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.forecast_vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]

  depends_on = [google_project_service.apis]
}

# Serverless VPC Connector — Cloud Run uses this to reach Cloud SQL
resource "google_vpc_access_connector" "connector" {
  name          = "forecast-vpc-cx-${var.environment}"
  region        = var.region
  ip_cidr_range = "10.8.0.0/28" # /28 required by connector
  network       = google_compute_network.forecast_vpc.name

  min_instances = 2 # GCP minimum
  max_instances = 3 # Keep costs down

  depends_on = [google_project_service.apis]
}
