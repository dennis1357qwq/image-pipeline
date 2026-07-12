variable "project_id" {
  description = "GCP project id."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "europe-west3"
}

variable "zone" {
  description = "GCP zone."
  type        = string
  default     = "europe-west3-a"
}

variable "deployment_name" {
  description = "Name prefix for all resources and generated benchmark config."
  type        = string
  default     = "image-pipeline-benchmark"
}

variable "ssh_user" {
  description = "Linux user used for SSH and benchmark remote commands."
  type        = string
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key registered on the VMs."
  type        = string
}

variable "repo_url" {
  description = "Git repository URL cloned by startup scripts."
  type        = string
}

variable "repo_branch" {
  description = "Git branch checked out by startup scripts."
  type        = string
  default     = "main"
}

variable "project_dir" {
  description = "Project directory on every VM."
  type        = string
  default     = "/opt/image-pipeline"
}

variable "machine_image_project" {
  description = "GCP image project for all VMs."
  type        = string
  default     = "ubuntu-os-cloud"
}

variable "machine_image_family" {
  description = "GCP image family for all VMs."
  type        = string
  default     = "ubuntu-2404-lts-amd64"
}

variable "main_machine_type" {
  description = "Machine type for the main node."
  type        = string
  default     = "e2-standard-4"
}

variable "worker_machine_type" {
  description = "Machine type for worker-only nodes."
  type        = string
  default     = "e2-standard-4"
}

variable "main_disk_size_gb" {
  description = "Boot disk size for the main node."
  type        = number
  default     = 50
}

variable "worker_disk_size_gb" {
  description = "Boot disk size for each worker node."
  type        = number
  default     = 30
}

variable "worker_node_count" {
  description = "Number of worker-only VMs."
  type        = number
  default     = 0
}

variable "main_default_workers" {
  description = "Default worker containers on the main node."
  type        = number
  default     = 2
}

variable "main_heavy_workers" {
  description = "Heavy worker containers on the main node."
  type        = number
  default     = 1
}

variable "worker_default_workers" {
  description = "Default worker containers on each worker-only node."
  type        = number
  default     = 0
}

variable "worker_heavy_workers" {
  description = "Heavy worker containers on each worker-only node."
  type        = number
  default     = 0
}

variable "postgres_user" {
  description = "Postgres username."
  type        = string
  default     = "postgres"
}

variable "postgres_password" {
  description = "Postgres password."
  type        = string
  sensitive   = true
}

variable "postgres_db" {
  description = "Postgres database name."
  type        = string
  default     = "image_pipeline"
}

variable "minio_root_user" {
  description = "MinIO root user."
  type        = string
  default     = "minioadmin"
}

variable "minio_root_password" {
  description = "MinIO root password."
  type        = string
  sensitive   = true
}

variable "object_storage_bucket" {
  description = "MinIO bucket used by the app."
  type        = string
  default     = "image-pipeline"
}

variable "max_queue_length" {
  description = "API admission-control queue length."
  type        = number
  default     = 1000
}

variable "redis_maxmemory" {
  description = "Redis maxmemory value used in docker-compose.main.yml."
  type        = string
  default     = "512mb"
}

variable "api_port" {
  description = "Public API port."
  type        = number
  default     = 8000
}

variable "allowed_ssh_cidrs" {
  description = "CIDR ranges allowed to SSH into the VMs."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "allowed_api_cidrs" {
  description = "CIDR ranges allowed to access the API."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "expose_minio" {
  description = "Whether to expose MinIO ports publicly. Keep false unless you need browser access."
  type        = bool
  default     = false
}

variable "generated_config_path" {
  description = "Local path for the generated benchmark cluster config."
  type        = string
  default     = "../../../benchmark/loadtest_runner/configs/gcp-generated.json"
}
