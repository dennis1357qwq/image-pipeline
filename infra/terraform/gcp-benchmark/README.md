# GCP Benchmark Terraform

This Terraform package provisions GCP VMs for the image-pipeline benchmark setup.

It supports:

- one main node running API, Redis, Postgres, MinIO, and optional workers
- `N` worker-only nodes running default/heavy workers against the main node
- configurable machine types, disk sizes, and worker counts
- generated `cluster_runner.py` config
- reproducible deployment profiles for 1-node, 2-node, 3-node, 4-node, and 5-node benchmark variants

## First Use

```bash
cd infra/terraform/gcp-benchmark
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`.

Then run:

```bash
terraform init
terraform plan
terraform apply
```

Terraform writes a generated benchmark config to:

```text
benchmark/loadtest_runner/configs/gcp-generated.json
```

Use the `single_run_command` output as a starting point.

The generated config contains the public SSH/API addresses and the remote project directory used by the benchmark runner.

## Deployment Profiles

Keep project-specific values, credentials, SSH settings, and CIDR allowlists in
`terraform.tfvars`. Select the node setup with an additional var file:

```bash
terraform plan \
  -var-file=terraform.tfvars \
  -var-file=deployments/1-node-main-4h-4d.tfvars
```

```bash
terraform plan \
  -var-file=terraform.tfvars \
  -var-file=deployments/2-node-main-4h-4d-worker-4h-4d.tfvars
```

```bash
terraform plan \
  -var-file=terraform.tfvars \
  -var-file=deployments/3-node-main-4h-4d-worker-4h-4d.tfvars
```

Use the same `-var-file` combination for `terraform apply` and `terraform destroy`.

Current profile types:

| Profile | Purpose |
| --- | --- |
| `1-node-main-4h-4d.tfvars` | Single-node baseline with main-node workers |
| `2-node-main-4h-4d-worker-4h-4d.tfvars` | Full 8 vCPU worker-node comparison |
| `3-node-main-4h-4d-worker-4h-4d.tfvars` | Full 8 vCPU worker-node comparison |
| `4-node-main-4h-4d-worker-4h-4d.tfvars` | Full 8 vCPU worker-node comparison |
| `2-node-main-4h-4d-worker-2h-2d.tfvars` | Mixed quota-constrained comparison |
| `3-node-main-4h-4d-worker-2h-2d.tfvars` | Mixed quota-constrained comparison |
| `4-node-main-4h-4d-worker-2h-2d.tfvars` | Mixed quota-constrained comparison |
| `5-node-main-4h-4d-worker-2h-2d.tfvars` | 5-node mixed deployment under CPU quota |

Example:

```bash
terraform apply \
  -var-file=terraform.tfvars \
  -var-file=deployments/5-node-main-4h-4d-worker-2h-2d.tfvars
```

Destroy the active deployment before switching to a materially different profile:

```bash
terraform destroy \
  -var-file=terraform.tfvars \
  -var-file=deployments/5-node-main-4h-4d-worker-2h-2d.tfvars
```

## Scaling

Change these values and apply again:

```hcl
main_machine_type        = "e2-standard-8"
worker_machine_type      = "e2-standard-4"
worker_node_count        = 2
main_default_workers     = 0
main_heavy_workers       = 0
worker_default_workers   = 2
worker_heavy_workers     = 1
```

For benchmark comparability, prefer a new `deployment_name` for materially
different setups.

## Quota Notes

The GCP project used during evaluation had a global CPU quota of 32 vCPUs.

A full 5-node deployment using `e2-standard-8` on every node requires:

```text
5 * 8 vCPU = 40 vCPU
```

For that reason, the 5-node benchmark profile uses a mixed setup:

```text
main node:    e2-standard-8
worker nodes: e2-standard-4
```

This keeps the deployment below the quota while still validating a 5-node cluster.

## Remote Connectivity

The benchmark runner uses non-interactive SSH. If a VM IP address is reused, remove the old host key locally before running a benchmark:

```bash
ssh-keygen -R <vm-ip>
ssh dennis-mac@<vm-ip> exit
```

Worker-only nodes connect to Redis, PostgreSQL, and MinIO on the main node's internal IP address. The internal firewall rule allows traffic inside the benchmark subnet.

## Manual Recovery

If a VM startup script fails during Docker build, the deployment can usually be recovered by rerunning Docker Compose on the affected VM.

Main node:

```bash
cd /opt/image-pipeline

DOCKER_BUILDKIT=0 docker compose --env-file infra/docker/.env.main \
  -f infra/docker/docker-compose.main.yml \
  up -d --build \
  --scale worker-default=4 \
  --scale worker-heavy=4
```

Worker node:

```bash
cd /opt/image-pipeline

DOCKER_BUILDKIT=0 docker compose --env-file infra/docker/.env.worker \
  -f infra/docker/docker-compose.worker.yml \
  up -d --build \
  --scale worker-default=2 \
  --scale worker-heavy=2
```
