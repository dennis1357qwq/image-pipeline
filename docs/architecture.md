# Architecture

This document describes the architecture of the Image Processing Pipeline, the responsibilities of each component, and the main design decisions behind the system.

---

# System Overview

The application is an asynchronous image processing pipeline. Clients submit images through a FastAPI service. The API stores the original image, creates persistent job metadata containing an image processing pipeline, and enqueues the job for background processing. Worker instances consume jobs from the queue, execute every processing step sequentially, store the processed image, and update the job status.

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
          +--------+ Pipeline Execution  |
                   +---------------------+
```

---

# Image Processing Pipeline

Unlike traditional image processing services that execute exactly one operation per request, every job in this system contains an image processing pipeline.

A pipeline is an ordered list of processing steps. Every processing step consists of:

- an operation
- a parameter set

The worker executes all processing steps sequentially on the same image.

```text
Input Image
      │
      ▼
Thumbnail
      │
      ▼
Blur
      │
      ▼
Sharpen
      │
      ▼
Edge Detection
      │
      ▼
Output Image
```

Each processing step is represented by the following logical structure:

```text
PipelineStep
├── operation
└── parameters
```

This architecture allows new image processing operations to be added without modifying the worker implementation. The worker simply executes the configured processing pipeline.

---

# Shared Processing Parameters

Most processing operations support optional shared parameters that modify how an operation is executed.

## repeat

The `repeat` parameter executes the same processing step multiple times before continuing with the next pipeline step.

This makes it possible to create computationally expensive workloads without introducing additional image processing algorithms.

## region

The `region` parameter limits processing to a rectangular part of the image.

Only the selected region is modified while the remainder of the image stays unchanged.

This enables localized image processing such as selective blurring.

---

# Component Responsibilities

## FastAPI

The API is the entry point for clients. It accepts image uploads, validates the requested processing pipeline, stores the image in object storage, creates job metadata in PostgreSQL, and enqueues the job ID in Redis.

The API is designed to remain stateless. It does not store uploaded files locally and does not keep job state in memory.

## Worker

Workers are long-running background processes. Each worker pulls jobs from Redis, loads the corresponding metadata from PostgreSQL, downloads the original image from MinIO, executes every processing step contained in the processing pipeline, uploads the result to MinIO, and updates the job status.

Workers are stateless and can be scaled horizontally.

## Redis Queue

Redis is used as a lightweight job queue. It stores only job IDs, not image data or full job metadata. This keeps queue entries small and allows workers to retrieve pending work asynchronously.

## PostgreSQL

PostgreSQL stores persistent job metadata, including the job ID, processing pipeline, input key, output key, and processing status. It is the source of truth for job state.

## MinIO

MinIO stores binary image data. Original images and processed results are stored as objects, while PostgreSQL only stores references to these objects.

## image_pipeline_common

The shared package contains common clients and data models used by both the API and the worker. This avoids duplicated Redis, PostgreSQL, object storage, and shared model logic.

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

1. A client uploads an image and submits an image processing pipeline.
2. The API validates the requested processing pipeline.
3. The API checks the current Redis queue length.
4. If the queue is full, the request is rejected with HTTP `429`.
5. Otherwise, the API stores the original image in MinIO.
6. The API creates a job record in PostgreSQL.
7. The API pushes the job ID to Redis.
8. A worker consumes the job ID from Redis.
9. The worker loads the job metadata from PostgreSQL.
10. The worker downloads the original image from MinIO.
11. The worker executes every processing step contained in the processing pipeline.
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

This prevents the system from accepting more work than the workers can process within a reasonable time.

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

This avoids leaving a job permanently stuck in `PENDING` without ever becoming visible to workers.

---

# Scalability Considerations

The main expected scaling target is the worker layer because image processing is the compute-intensive part of the application.

The introduction of configurable processing pipelines enables workloads with significantly different computational costs.

Simple jobs such as grayscale conversion finish within only a few milliseconds, while pipelines containing repeated blur operations or multiple processing stages require substantially more CPU time.

This workload variability provides a realistic foundation for evaluating horizontal worker scaling during scalability experiments.

The system is designed so that additional worker instances can consume jobs from the same Redis queue. This allows processing capacity to increase while keeping API request handling, metadata storage, object storage, and job scheduling separated.

Stateful components may become bottlenecks as throughput increases. In particular:

- Redis may become a queueing bottleneck.
- PostgreSQL may become a metadata update bottleneck.
- MinIO may become an object storage or network bottleneck.

These limitations should be evaluated during scalability experiments.

---

# Future Extensions

The pipeline abstraction provides a stable foundation for future extensions without requiring architectural changes.

Potential future enhancements include:

- additional image processing operations
- AI-based image processing
- multi-stage processing workflows
- workload-specific scheduling strategies
- workload isolation for different job classes
