# Development Guide

This document contains useful information for local development, testing, benchmarking, and debugging of the Image Processing Pipeline.

---

# Project Structure

```text
image-pipeline/
├── api/                     # FastAPI service
├── worker/                  # Background worker
├── image_pipeline_common/   # Shared clients and models
├── benchmark/               # Benchmark definitions
├── scripts/                 # Utility scripts
├── infra/                   # Docker Compose and infrastructure
├── docs/                    # Documentation
└── results/                 # Benchmark and experiment results
```

---

# Running the Infrastructure

To start the complete infrastructure (Redis, PostgreSQL, MinIO, API, and Worker):

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

Run everything in the background:

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Stop all services:

```bash
docker compose -f infra/docker/docker-compose.yml down
```

---

# Useful Docker Commands

View logs of all services:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f
```

View logs of a single service:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f worker
```

Restart a service:

```bash
docker compose -f infra/docker/docker-compose.yml restart worker
```

Rebuild and recreate a service:

```bash
docker compose -f infra/docker/docker-compose.yml up --build --force-recreate worker
```

Stop a service:

```bash
docker compose -f infra/docker/docker-compose.yml stop worker
```

Start it again:

```bash
docker compose -f infra/docker/docker-compose.yml start worker
```

---

# Running Components Locally

The infrastructure can remain inside Docker while individual services are executed locally.

## API

```bash
cd api
source .venv/bin/activate
PYTHONPATH=.. uvicorn app.main:app --reload --port 8000
```

## Worker

```bash
cd worker
source .venv/bin/activate
PYTHONPATH=.. python3 -m app.worker
```

The `PYTHONPATH=..` setting allows both services to import the shared package `image_pipeline_common`.

---

# End-to-End Testing

The recommended workflow is:

1. Start the infrastructure.
2. Open Swagger UI.
3. Submit a `POST /jobs` request.
4. Upload an image.
5. Configure the processing pipeline.
6. Execute the request.
7. Poll `GET /jobs/{job_id}` until the status becomes `DONE`.
8. Download the processed image using `GET /jobs/{job_id}/result`.

---

# Benchmarking

The project contains a standalone benchmark utility for measuring the computational cost of different processing pipelines.

The benchmark executes predefined workloads multiple times and records wall-clock and CPU execution times.

Example:

```bash
PYTHONPATH=.:worker python3 scripts/benchmark_operations.py \
    --image worker/examples/test.png \
    --iterations 20 \
    --warmup 3 \
    --shuffle \
    --output results/local/operation-benchmark.csv
```

## Benchmark Parameters

| Parameter      | Description                                           |
| -------------- | ----------------------------------------------------- |
| `--image`      | Input image used for benchmarking                     |
| `--iterations` | Number of measured executions                         |
| `--warmup`     | Warm-up executions excluded from measurements         |
| `--shuffle`    | Randomizes benchmark order to reduce ordering effects |
| `--output`     | Output CSV file                                       |

Warm-up iterations reduce initialization overhead, while randomized execution order helps minimize systematic bias caused by cache effects or CPU frequency scaling.

Benchmark results should **not** be committed to the repository because they depend on the local hardware and execution environment.

---

# Benchmark Results

The repository contains the following directories for benchmark results:

```text
results/
├── local/
├── docker/
└── gcp/
```

These directories are intended for measurements collected in different environments during scalability experiments.

---

# Available Services

| Service       | Address                    |
| ------------- | -------------------------- |
| API           | http://localhost:8000      |
| Swagger UI    | http://localhost:8000/docs |
| MinIO API     | http://localhost:9000      |
| MinIO Console | http://localhost:9001      |
| PostgreSQL    | localhost:5432             |
| Redis         | localhost:6379             |

---

# Shared Code

The `image_pipeline_common` package contains shared implementations used by both the API and the worker.

It currently provides:

- Redis queue client
- PostgreSQL job repository
- Object storage client
- Shared data models
- Pipeline models

This avoids duplicated infrastructure logic and ensures consistent behaviour across services.

---

# Troubleshooting

## Import Errors

When running services locally, ensure that the project root is included in the Python path.

For example:

```bash
PYTHONPATH=..
```

or for benchmark scripts:

```bash
PYTHONPATH=.:worker
```

---

## Changes Are Not Reflected Inside Docker

Rebuild the affected service:

```bash
docker compose -f infra/docker/docker-compose.yml up --build --force-recreate <service>
```

or rebuild the complete project:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

---

## Viewing Logs

Inspect logs of all running services:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f
```

Inspect a single service:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f worker
```
