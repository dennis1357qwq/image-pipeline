# Architecture

This document describes the architecture of the Image Processing Pipeline, the responsibilities of each component, and the main design decisions behind the system.

---

# System Overview

The application is an asynchronous image processing pipeline. Clients submit images through a FastAPI service. The API stores the original image, creates persistent job metadata, and enqueues the job for background processing. Worker instances consume jobs from the queue, process the images, store the result, and update the job status.

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

# Component Responsibilities

## FastAPI

The API is the entry point for clients. It accepts image uploads, validates the requested operation, stores the image in object storage, creates job metadata in PostgreSQL, and enqueues the job ID in Redis.

The API is designed to remain stateless. It does not store uploaded files locally and does not keep job state in memory.

## Worker

Workers are long-running background processes. Each worker pulls jobs from Redis, loads the corresponding metadata from PostgreSQL, downloads the original image from MinIO, processes it, uploads the result to MinIO, and updates the job status.

Workers are stateless and can be scaled horizontally.

## Redis Queue

Redis is used as a lightweight job queue. It stores only job IDs, not image data or full job metadata. This keeps queue entries small and allows workers to retrieve pending work asynchronously.

## PostgreSQL

PostgreSQL stores persistent job metadata, including the job ID, operation, input key, output key, and processing status. It is the source of truth for job state.

## MinIO

MinIO stores binary image data. Original images and processed results are stored as objects, while PostgreSQL only stores references to these objects.

## image_pipeline_common

The shared package contains common clients and data models used by both the API and the worker. This avoids duplicated Redis, PostgreSQL, and object storage logic.

---

# Stateful and Stateless Components

The system separates stateless compute components from stateful storage components.

## Stateless Components

- FastAPI service
- Worker instances

These components can be restarted or replicated without losing application state.

## Stateful Components

- PostgreSQL
- MinIO
- Redis

PostgreSQL stores persistent job metadata, MinIO stores image objects, and Redis stores the current queue backlog.

---

# Job Lifecycle

1. A client uploads an image and selects an operation.
2. The API validates the requested operation.
3. The API checks the current Redis queue length.
4. If the queue is full, the request is rejected with HTTP `429`.
5. Otherwise, the API stores the original image in MinIO.
6. The API creates a job record in PostgreSQL.
7. The API pushes the job ID to Redis.
8. A worker consumes the job ID from Redis.
9. The worker loads the job metadata from PostgreSQL.
10. The worker downloads the original image from MinIO.
11. The worker processes the image.
12. The worker uploads the processed image to MinIO.
13. The worker marks the job as `DONE` in PostgreSQL.
14. The client can retrieve the result through the API.

---

# Admission Control and Backpressure

To prevent unbounded queue growth, the API implements queue-length-based admission control.

Before accepting a new job, the API checks the current Redis queue length. If the number of queued jobs is greater than or equal to the configured `MAX_QUEUE_LENGTH`, the API rejects the request with:

```text
429 Too Many Requests
```

This prevents the system from accepting more work than the workers can process in a reasonable time.

The queue limit is configured through an environment variable:

```text
MAX_QUEUE_LENGTH=100
```

The current value is a development default and should be tuned empirically during scalability experiments based on worker throughput and acceptable queueing delay.

---

# Queue Failure Handling

Admission control reduces the likelihood of queue overload, but the final enqueue operation can still fail, for example if Redis becomes unavailable or reaches its memory limit.

The API handles this case defensively:

1. The image is uploaded to MinIO.
2. The job metadata is created in PostgreSQL.
3. The API attempts to push the job ID to Redis.
4. If the Redis push fails, the job is marked as `FAILED`.
5. The API returns:

```text
503 Service Unavailable
```

This avoids leaving a job permanently stuck in `PENDING` without ever being visible to workers.

---

# Scalability Considerations

The main expected scaling target is the worker layer, because image processing is the compute-heavy part of the application.

The system is designed so that additional worker instances can consume jobs from the same Redis queue. This allows the processing capacity to increase while keeping API request handling, metadata storage, object storage, and job scheduling separated.

Stateful components may become bottlenecks as throughput increases. In particular:

- Redis may become a queueing bottleneck.
- PostgreSQL may become a metadata update bottleneck.
- MinIO may become an object storage or network bottleneck.

These limitations should be evaluated during scalability experiments.
