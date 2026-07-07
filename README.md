# Image Processing Pipeline

A distributed image processing system built with **FastAPI**, **Redis**, **PostgreSQL**, and **MinIO**. Images are uploaded through a REST API, processed asynchronously by worker instances, and stored in object storage.

The project is designed with scalability in mind by separating compute, metadata storage, object storage, and job scheduling into dedicated components. Image processing jobs are defined as configurable processing pipelines consisting of one or more processing steps.

---

# Overview

The system consists of the following components:

- **FastAPI** – Receives client requests, validates processing pipelines, and creates processing jobs.
- **Redis** – Stores pending jobs in dedicated processing queues.
- **PostgreSQL** – Stores persistent job metadata and processing status.
- **MinIO** – Stores original and processed images.
- **Default Worker** – Processes standard image processing workloads.
- **Heavy Worker** – Processes computationally expensive workloads.
- **image_pipeline_common** – Shared library containing common clients, models, retry logic, and shared interfaces used by both the API and the workers.

---

# Architecture

```text
                +-------------+
                |   Client    |
                +------+------+
                       |
                       v
                +-------------+
                |   FastAPI   |
                +------+------+
                       |
          +------------+-------------+
          |            |             |
          v            v             v
   +-------------+ +---------+ +--------------+
   | PostgreSQL  | |  MinIO  | | Redis Queue  |
   | (Metadata)  | | (Images)| |  (Job IDs)   |
   +------+------+ +----+----+ +------+-------+
          ^             ^            |
          |             |            |
          |             |            v
          |        +-----+---------------+
          |        |      Worker(s)      |
          +--------+   Image Processing  |
                   |       Pipeline      |
                   |    Default/Heavy    |
                   +---------------------+
```

---

# Repository Structure

```text
image-pipeline/
├── api/
├── worker/
├── image_pipeline_common/
├── benchmark/
├── scripts/
├── infra/
├── docs/
└── results/
```

---

# Getting Started

## Prerequisites

- Docker
- Docker Compose

## Start the complete system

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

After startup:

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- MinIO Console: http://localhost:9001

---

# API Endpoints

| Method | Endpoint                | Description                                 |
| ------ | ----------------------- | ------------------------------------------- |
| POST   | `/jobs`                 | Upload an image and create a processing job |
| GET    | `/jobs/{job_id}`        | Retrieve job metadata and status            |
| GET    | `/jobs/{job_id}/result` | Download the processed image                |
| GET    | `/health`               | Health check endpoint                       |

---

# Example Processing Pipeline

Each job contains a processing pipeline consisting of one or more ordered processing steps.

Example:

```json
[
  {
    "operation": "thumbnail",
    "parameters": {
      "width": 600,
      "height": 600
    }
  },
  {
    "operation": "blur",
    "parameters": {
      "radius": 6,
      "repeat": 5
    }
  }
]
```

The worker executes every pipeline step sequentially on the same image.

---

# Job Lifecycle

1. A client uploads an image and submits an image processing pipeline.
2. The API validates the requested pipeline.
3. The API stores the original image in MinIO.
4. The API stores the job metadata in PostgreSQL.
5. The job ID is pushed to the Redis queue.
6. A worker retrieves the job from Redis.
7. The worker downloads the original image from MinIO.
8. Every pipeline step is executed sequentially.
9. The processed image is uploaded to MinIO.
10. The worker marks the job as `DONE` in PostgreSQL.
11. The client retrieves the processed image through the API.

---

# Scalability Features

The current implementation already incorporates several distributed systems principles aimed at improving scalability and resilience.

### Asynchronous Processing

Jobs are processed asynchronously through Redis, decoupling request handling from image processing.

### Admission Control

The API limits queue growth by rejecting new requests once a configurable queue length is reached.

### Workload Isolation

Jobs are classified into different Redis queues based on their expected computational cost.

Separate worker pools process lightweight and computationally expensive jobs independently, preventing long-running jobs from delaying short requests.

### Idempotent Job Creation

Clients may provide an `Idempotency-Key` when creating jobs.

Repeated requests with the same key and identical payload return the previously created job instead of creating duplicate work. Requests using the same key with different payloads are rejected.

### Structured Observability

Both the API and workers emit structured JSON logs containing queue assignment, processing status, execution times, queue waiting time, and retry events.

### Retry with Exponential Backoff and Jitter

Workers automatically retry transient object storage operations using exponential backoff combined with randomized jitter to reduce retry synchronization under failures.

---

# Supported Operations

Currently supported processing operations include:

- Grayscale
- Thumbnail
- Blur
- Rotate
- Sharpen
- Contrast
- Edge Detection
- Emboss

Several operations additionally support configurable parameters such as processing regions and repeated execution.

---

# Design Decisions

The system intentionally separates responsibilities across different services.

- **Redis** stores lightweight job identifiers and acts as the scheduling queue.
- **PostgreSQL** stores persistent job metadata and processing status.
- **MinIO** stores binary image data rather than embedding images inside database records.
- **Workers** remain stateless and execute arbitrary processing pipelines.
- **Shared clients and models** are implemented in `image_pipeline_common` to avoid duplicated logic.
- **Idempotency keys** prevent duplicate job creation during repeated client requests.
- **Dedicated worker pools** isolate lightweight and computationally expensive workloads.
- **Structured JSON logging** provides detailed operational visibility and supports performance evaluation.
- **Retries with exponential backoff and jitter** improve resilience against transient infrastructure failures.

This separation allows each component to scale independently while maintaining clear responsibilities.

---

# Further Documentation

Additional documentation is available in the `docs/` directory.

- [Architecture](docs/architecture.md)
- [Development Guide](docs/development.md)
- [Image Operations](docs/image-operations.md)
- Scalability Evaluation _(coming soon)_
