output "api_url" {
  description = "Public API URL for benchmarks and manual tests."
  value       = "http://${google_compute_instance.main.network_interface[0].access_config[0].nat_ip}:${var.api_port}"
}

output "main_external_ip" {
  description = "External IP of the main node."
  value       = google_compute_instance.main.network_interface[0].access_config[0].nat_ip
}

output "main_internal_ip" {
  description = "Internal IP of the main node."
  value       = google_compute_instance.main.network_interface[0].network_ip
}

output "worker_external_ips" {
  description = "External IPs of worker-only nodes."
  value = [
    for node in google_compute_instance.worker :
    node.network_interface[0].access_config[0].nat_ip
  ]
}

output "worker_internal_ips" {
  description = "Internal IPs of worker-only nodes."
  value = [
    for node in google_compute_instance.worker :
    node.network_interface[0].network_ip
  ]
}

output "benchmark_config_path" {
  description = "Generated local cluster config consumed by cluster_runner.py."
  value       = local_file.benchmark_config.filename
}

output "single_run_command" {
  description = "Example single benchmark command."
  value = join(" ", [
    "benchmark/venv/bin/python -m benchmark.loadtest_runner.cluster_runner",
    "--config ${local_file.benchmark_config.filename}",
    "--profile representative_mixed",
    "--rate 1",
    "--duration 60s",
    "--main-node-default-workers ${var.main_default_workers}",
    "--main-node-heavy-workers ${var.main_heavy_workers}",
    "--worker-node-default-workers ${var.worker_default_workers}",
    "--worker-node-heavy-workers ${var.worker_heavy_workers}",
    "--remote-python benchmark/venv/bin/python",
  ])
}

