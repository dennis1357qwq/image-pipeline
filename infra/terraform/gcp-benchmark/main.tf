locals {
  main_name      = "${var.deployment_name}-main"
  worker_names   = [for index in range(var.worker_node_count) : "${var.deployment_name}-worker-${index + 1}"]
  ssh_public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
  startup_common = {
    project_dir           = var.project_dir
    repo_url              = var.repo_url
    repo_branch           = var.repo_branch
    postgres_user         = var.postgres_user
    postgres_password     = var.postgres_password
    postgres_db           = var.postgres_db
    minio_root_user       = var.minio_root_user
    minio_root_password   = var.minio_root_password
    object_storage_bucket = var.object_storage_bucket
  }
}

data "google_compute_image" "vm" {
  family  = var.machine_image_family
  project = var.machine_image_project
}

resource "google_compute_network" "benchmark" {
  name                    = "${var.deployment_name}-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "benchmark" {
  name          = "${var.deployment_name}-subnet"
  ip_cidr_range = "10.42.0.0/24"
  region        = var.region
  network       = google_compute_network.benchmark.id
}

resource "google_compute_firewall" "ssh" {
  name    = "${var.deployment_name}-allow-ssh"
  network = google_compute_network.benchmark.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.allowed_ssh_cidrs
  target_tags   = ["${var.deployment_name}-ssh"]
}

resource "google_compute_firewall" "api" {
  name    = "${var.deployment_name}-allow-api"
  network = google_compute_network.benchmark.name

  allow {
    protocol = "tcp"
    ports    = [tostring(var.api_port)]
  }

  source_ranges = var.allowed_api_cidrs
  target_tags   = ["${var.deployment_name}-api"]
}

resource "google_compute_firewall" "internal" {
  name    = "${var.deployment_name}-allow-internal"
  network = google_compute_network.benchmark.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "icmp"
  }

  source_ranges = [google_compute_subnetwork.benchmark.ip_cidr_range]
}

resource "google_compute_firewall" "minio" {
  count   = var.expose_minio ? 1 : 0
  name    = "${var.deployment_name}-allow-minio"
  network = google_compute_network.benchmark.name

  allow {
    protocol = "tcp"
    ports    = ["9000", "9001"]
  }

  source_ranges = var.allowed_api_cidrs
  target_tags   = ["${var.deployment_name}-minio"]
}

resource "google_compute_instance" "main" {
  name         = local.main_name
  machine_type = var.main_machine_type
  zone         = var.zone
  tags = compact([
    "${var.deployment_name}-ssh",
    "${var.deployment_name}-api",
    var.expose_minio ? "${var.deployment_name}-minio" : "",
  ])

  boot_disk {
    initialize_params {
      image = data.google_compute_image.vm.self_link
      size  = var.main_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.benchmark.id

    access_config {
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_user}:${local.ssh_public_key}"
  }

  metadata_startup_script = templatefile("${path.module}/templates/startup-main.sh.tftpl", merge(
    local.startup_common,
    {
      ssh_user             = var.ssh_user
      main_default_workers = var.main_default_workers
      main_heavy_workers   = var.main_heavy_workers
      max_queue_length     = var.max_queue_length
      redis_maxmemory      = var.redis_maxmemory
    }
  ))
}

resource "google_compute_instance" "worker" {
  count        = var.worker_node_count
  name         = local.worker_names[count.index]
  machine_type = var.worker_machine_type
  zone         = var.zone
  tags         = ["${var.deployment_name}-ssh"]

  boot_disk {
    initialize_params {
      image = data.google_compute_image.vm.self_link
      size  = var.worker_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.benchmark.id

    access_config {
    }
  }

  metadata = {
    ssh-keys = "${var.ssh_user}:${local.ssh_public_key}"
  }

  metadata_startup_script = templatefile("${path.module}/templates/startup-worker.sh.tftpl", merge(
    local.startup_common,
    {
      ssh_user               = var.ssh_user
      main_node_host         = google_compute_instance.main.network_interface[0].network_ip
      worker_default_workers = var.worker_default_workers
      worker_heavy_workers   = var.worker_heavy_workers
    }
  ))
}

resource "local_file" "benchmark_config" {
  filename = "${path.module}/${var.generated_config_path}"
  content = templatefile("${path.module}/templates/cluster-config.json.tftpl", {
    name         = var.deployment_name
    api_url      = "http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:${var.api_port}"
    ssh_user     = var.ssh_user
    project_dir  = var.project_dir
    main_name    = "main-node"
    main_host    = google_compute_instance.main.network_interface[0].access_config[0].nat_ip
    worker_nodes = google_compute_instance.worker
  })
}
