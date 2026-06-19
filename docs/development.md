# Development Guide

This document contains useful information for local development, testing, and debugging of the Image Processing Pipeline.

---

# Project Structure

```text
image-pipeline/
├── api/                     # FastAPI service
├── worker/                  # Background worker
├── image_pipeline_common/   # Shared clients and models
├── infra/                   # Docker Compose and infrastructure
└── docs/                    # Project documentation
```

---

# Running the Infrastructure

To start the required infrastructure components (Redis, PostgreSQL, MinIO, API, Worker):

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

To run the services in the background:

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

Stop all services:

```bash
docker compose -f infra/docker/docker-compose.yml down
```

---

# Useful Docker Commands

View logs:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f
```

Restart a single service:

```bash
docker compose -f infra/docker/docker-compose.yml restart worker
```

Rebuild and restart a single service:

```bash
docker compose -f infra/docker/docker-compose.yml up --build worker
```

Stop a single service:

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

The `PYTHONPATH=..` setting ensures that the shared package `image_pipeline_common` can be imported when running services outside Docker.

---

# Testing the System

The recommended end-to-end workflow is:

1. Start the system.
2. Open Swagger UI at `http://localhost:8000/docs`.
3. Submit a `POST /jobs` request with an image and an operation.
4. Poll `GET /jobs/{job_id}` until the status becomes `DONE`.
5. Retrieve the processed image via `GET /jobs/{job_id}/result`.

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

The package `image_pipeline_common` contains shared implementations used by both the API and the worker.

It currently provides:

- Redis queue client
- PostgreSQL job repository
- Object storage client
- Shared data models

This avoids duplicated logic and keeps the behaviour of both services consistent.

---

# Troubleshooting

## Import errors for `image_pipeline_common`

When running services locally, make sure to include:

```bash
PYTHONPATH=..
```

before the execution command.

## Changes are not reflected inside Docker

Rebuild the affected service:

```bash
docker compose -f infra/docker/docker-compose.yml up --build <service>
```

or rebuild the entire project:

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

## Viewing logs

To inspect all running services:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f
```

To inspect only a single service:

```bash
docker compose -f infra/docker/docker-compose.yml logs -f worker
```
