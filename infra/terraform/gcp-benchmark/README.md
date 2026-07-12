# GCP Benchmark Terraform

This Terraform package provisions GCP VMs for the image-pipeline benchmark setup.

It supports:

- one main node running API, Redis, Postgres, MinIO, and optional workers
- `N` worker-only nodes running default/heavy workers against the main node
- configurable machine types, disk sizes, and worker counts
- generated `cluster_runner.py` config

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

