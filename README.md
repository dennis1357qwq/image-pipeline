# Image Processing Pipeline

A distributed image processing system built with **FastAPI**, **Redis**, **PostgreSQL**, and **MinIO**. Images are uploaded through a REST API, processed asynchronously by worker instances, and stored in object storage.

The project is designed with scalability in mind by separating metadata storage, object storage, and job scheduling into dedicated components.

---

# Overview

The system consists of the following components:

- **FastAPI** – Receives client requests and creates processing jobs.
- **Redis** – Stores pending jobs in a queue for asynchronous processing.
- **PostgreSQL** – Stores job metadata and processing status.
- **MinIO** – Stores original and processed images.
- **Worker** – Consumes jobs from Redis, processes images, and stores the results.
- **image_pipeline_common** – Shared library containing common clients and models used by both the API and the worker.

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
          +--------+  Image Processing   |
                   +---------------------+
```

---

# Repository Structure

```text
image-pipeline/
├── api/                     # FastAPI service
├── worker/                  # Background worker
├── image_pipeline_common/   # Shared clients and models
├── infra/                   # Docker Compose and infrastructure setup
└── docs/                    # Additional documentation
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

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- MinIO Console: `http://localhost:9001`

---

# API Endpoints

| Method | Endpoint                | Description                                 |
| ------ | ----------------------- | ------------------------------------------- |
| `POST` | `/jobs`                 | Upload an image and create a processing job |
| `GET`  | `/jobs/{job_id}`        | Retrieve job metadata and status            |
| `GET`  | `/jobs/{job_id}/result` | Download the processed image                |
| `GET`  | `/health`               | Health check endpoint                       |

---

# Job Lifecycle

1. A client uploads an image and specifies a processing operation.
2. The API stores the image in MinIO.
3. The API stores the job metadata in PostgreSQL.
4. The job ID is pushed to the Redis queue.
5. A worker retrieves the job from Redis.
6. The worker downloads the original image from MinIO.
7. The requested image operation is executed.
8. The processed image is uploaded to MinIO.
9. The worker marks the job as `DONE` in PostgreSQL.
10. The client can retrieve both the job status and the processed image through the API.

---

# Supported Operations

Currently supported image transformations:

- Grayscale (string: "grayscale")
- Thumbnail generation (string: "thumbnail")
- Blur (string: "blur")

---

# Design Decisions

The system intentionally separates responsibilities across different services:

- **Redis** stores only lightweight job identifiers and acts as the scheduling queue.
- **PostgreSQL** stores persistent job metadata and processing status.
- **MinIO** stores binary image data instead of embedding it in database records.
- **Shared clients and models** are implemented in `image_pipeline_common` to avoid duplicated logic between the API and worker components.

This separation enables independent scaling of services and keeps individual components focused on a single responsibility.

---

# Further Documentation

Additional developer documentation, local development instructions, and infrastructure details can be found in the `docs/` directory.
