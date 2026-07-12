# Architecture

This document describes the architecture of the Image Processing Pipeline, the responsibilities of each component, and the distributed systems principles implemented throughout the project.

The application is designed as an asynchronous image processing system that separates compute resources from persistent storage. This separation enables horizontal scaling of workers while keeping application state centralized.

---

# System Overview

Clients upload images together with a configurable processing pipeline through the FastAPI service. The API validates the request, stores the original image in object storage, persists job metadata, and enqueues the job for asynchronous processing.

Workers continuously consume jobs from Redis, execute the requested processing pipeline, upload the processed image, and update the job status.

The current architecture also separates lightweight and computationally expensive jobs into different worker pools through workload isolation.

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
          +----------------+----------------+
          |                |                |
          v                v                v
   +-------------+   +----------+   +---------------+
   | PostgreSQL  |   |  MinIO   |   |     Redis     |
   |  Metadata   |   |  Images  |   |    Queues     |
   +------+------+   +----+-----+   +------+--------+
          ^               ^                 |
          |               |        +--------+--------+
          |               |        |                 |
          |               |        v                 v
          |          +-----------+           +-----------+
          +----------| Worker    |           | Worker    |
                     | Default   |           | Heavy     |
                     +-----------+           +-----------+
```

---

# Component Responsibilities

## FastAPI

The API is the public entry point of the system.

Its responsibilities include:

- validating incoming processing pipelines
- storing uploaded images in MinIO
- creating persistent job metadata
- selecting the appropriate processing queue
- enforcing admission control
- handling idempotent requests
- returning job metadata and processed images

The API remains completely stateless and therefore can be replicated horizontally without synchronization.

---

## Worker

Workers perform all computational work.

Each worker continuously:

1. retrieves a job ID from Redis
2. loads the corresponding metadata
3. downloads the original image
4. executes the complete processing pipeline
5. uploads the processed image
6. updates the job status

Workers never store persistent state locally and can therefore be added or removed dynamically.

---

## Redis

Redis acts as the asynchronous messaging layer between the API and the worker pools.

Instead of storing complete job descriptions, Redis stores only lightweight job identifiers.

This keeps queue operations fast while PostgreSQL remains the source of truth for job metadata.

The current implementation uses two independent queues:

- `jobs:default`
- `jobs:heavy`

---

## PostgreSQL

PostgreSQL stores all persistent metadata associated with a processing job.

Stored information includes:

- job identifier
- processing pipeline
- input object key
- output object key
- processing status
- idempotency information
- creation timestamp

PostgreSQL represents the authoritative state of every job.

---

## MinIO

MinIO stores binary image data.

Original uploads and processed images are stored as objects while PostgreSQL stores only references to these objects.

This avoids storing large binary objects inside the relational database.

---

## image_pipeline_common

The shared package contains common implementations used by both the API and the workers.

It includes:

- Redis client
- PostgreSQL repository
- object storage client
- retry implementation
- shared models
- pipeline definitions

This avoids duplicated infrastructure logic and guarantees consistent behaviour across services.

---

# Stateful and Stateless Components

The architecture deliberately separates compute from persistent state.

## Stateless Components

- FastAPI
- Worker instances

These components can be restarted or replicated at any time without losing application state.

## Stateful Components

- PostgreSQL
- MinIO
- Redis

Redis stores queued work, PostgreSQL stores persistent metadata, and MinIO stores binary image objects.

Keeping state centralized enables horizontal scaling of the compute layer.

---

# Image Processing Pipeline

Unlike traditional image processing APIs that execute a single operation per request, every submitted job contains an ordered processing pipeline.

Each processing step consists of:

- an operation
- a parameter set

Example:

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

Every step operates on the output of the previous step until the complete pipeline has been executed.

Each processing step is represented as

```text
PipelineStep
├── operation
└── parameters
```

The worker implementation is independent of individual image operations.

Adding new processing operations only requires registering a new processing function without modifying the worker itself.

---

# Shared Processing Parameters

Several image operations support common optional parameters.

## repeat

The `repeat` parameter executes the same operation multiple times before continuing with the next pipeline step.

Besides increasing the visual effect of certain operations, this parameter intentionally allows the generation of computationally expensive workloads for scalability experiments.

## region

The `region` parameter restricts processing to a rectangular part of the image.

Only the selected area is modified while the remaining image remains unchanged.

This enables localized processing without introducing specialized image operations.

---

# Request Lifecycle

The complete lifecycle of a processing request is illustrated below.

1. A client uploads an image together with a processing pipeline.
2. The API validates the requested pipeline.
3. The API determines whether the workload should be processed by the default or heavy worker pool.
4. The API checks the corresponding queue length.
5. If admission control allows the request, the image is stored in MinIO.
6. Job metadata is written to PostgreSQL.
7. The job identifier is pushed to the appropriate Redis queue.
8. A worker retrieves the job ID.
9. The worker loads the corresponding metadata.
10. The worker downloads the original image.
11. Every processing step is executed sequentially.
12. The processed image is uploaded to MinIO.
13. The worker updates the job status.
14. The client retrieves the completed image through the API.

---

# Admission Control and Backpressure

The API implements queue-length-based admission control to prevent unbounded queue growth.

Before accepting a new job, the API determines the target queue and checks its current length.

If the queue already contains the configured maximum number of jobs, the request is rejected with

```text
429 Too Many Requests
```

This prevents the system from accepting more work than the worker pool can process within a reasonable amount of time.

The maximum queue length is configured using

```text
MAX_QUEUE_LENGTH
```

The local Docker Compose default is intentionally lower than the benchmark deployment default. The GCP Terraform deployment uses a larger value so that benchmark runs expose throughput and latency behavior before admission control starts rejecting requests.

Different worker pools maintain independent queue limits.

Consequently, a heavily loaded queue does not automatically block requests targeting another queue.

---

# Workload Isolation

Different image processing pipelines require vastly different computational effort.

For example, a simple grayscale conversion completes within only a few milliseconds, while repeated Gaussian blur operations may require several hundred milliseconds.

Without workload isolation, expensive jobs can significantly increase the waiting time of lightweight jobs.

To reduce this interference, the system separates workloads into two independent Redis queues:

```text
jobs:default
jobs:heavy
```

The API determines the appropriate queue before enqueuing a job.

Currently, pipelines are classified as heavy if a processing step contains

```text
repeat >= 5
```

The Docker deployment starts two independent worker pools.

```text
Worker Default
        │
        ▼
 jobs:default

Worker Heavy
        │
        ▼
 jobs:heavy
```

Each worker consumes jobs exclusively from its configured queue.

This prevents computationally expensive workloads from delaying lightweight requests while still allowing both worker pools to scale independently.

The workload classification can easily be extended in the future to include additional image operations or more advanced scheduling policies.

---

# Idempotency

Distributed systems must tolerate duplicate client requests.

For example, duplicate submissions may occur because

- a user clicks the submit button multiple times,
- a browser retries a request,
- a reverse proxy retries a timed-out request,
- a client library automatically retries failed requests.

To prevent duplicate job creation, the API supports idempotent request processing.

Clients may provide an

```text
Idempotency-Key
```

HTTP header when submitting a job.

The API computes a request hash consisting of

- the complete processing pipeline
- the SHA-256 hash of the uploaded image

If a request with the same idempotency key already exists, the stored request hash is compared against the newly received request.

Two situations are possible.

### Identical request

If both request hashes match, the API immediately returns the existing job instead of creating a duplicate.

### Different request

If the request hashes differ, the API rejects the request with

```text
409 Conflict
```

This prevents accidental reuse of an idempotency key for different jobs.

The implementation also handles concurrent requests safely using PostgreSQL's unique constraint on the idempotency key.

---

# Retry with Exponential Backoff and Jitter

Communication with external services may fail temporarily.

Typical examples include

- temporary network failures,
- object storage connection timeouts,
- transient infrastructure overload.

Immediately failing the entire job would unnecessarily reduce system availability.

Instead, workers automatically retry selected storage operations.

The retry mechanism provides

- configurable retry limits,
- exponential backoff,
- randomized jitter,
- structured retry logging.

The exponential backoff gradually increases the waiting time between retry attempts.

Randomized jitter introduces a small random delay to prevent multiple workers from retrying simultaneously after a shared failure.

This significantly reduces the probability of retry storms during transient infrastructure outages.

Only operations that are safe to execute multiple times are wrapped with retry logic.

Currently this includes downloading and uploading objects to MinIO.

The API intentionally does not retry client requests automatically.

Instead, retry decisions remain under client control, while idempotency guarantees ensure that repeated requests do not create duplicate jobs.

---

# Structured Observability

Both the API and the worker emit structured JSON logs instead of unstructured console output.

Every log entry contains an event type together with contextual metadata, allowing logs to be filtered, aggregated, and analyzed automatically.

Typical API events include

- `job_created`
- `idempotency_hit`
- `idempotency_conflict`

Worker events include

- `job_picked`
- `job_finished`
- `job_failed`
- `retry_scheduled`
- `retry_success`

Successful job execution additionally records several timing metrics, including

- queue waiting time
- object download time
- image processing time
- object upload time
- total worker execution time

These metrics provide visibility into where processing time is spent and form the basis for later scalability evaluation.

---

# Queue Failure Handling

Admission control reduces the likelihood of queue overload, but enqueueing may still fail due to temporary Redis failures.

The API handles this case defensively.

1. The image is uploaded to MinIO.
2. The job metadata is stored in PostgreSQL.
3. The API attempts to enqueue the job.
4. If Redis rejects the operation, the job status is updated to `FAILED`.
5. The API returns

```text
503 Service Unavailable
```

This prevents jobs from remaining indefinitely in the `PENDING` state without ever becoming visible to workers.

---

# Scalability Considerations

The architecture is designed around independent scaling of compute and storage components.

The primary scalability target is the worker layer because image processing dominates the computational cost of the application.

Horizontal scaling is achieved by adding additional worker instances.

Since workers are completely stateless, they can be replicated without requiring synchronization between instances.

Workload isolation further improves scalability by separating lightweight and computationally intensive jobs into different worker pools.

This reduces queue interference and prevents long-running jobs from delaying short-running requests.

The API remains lightweight because it performs only request validation, persistence, and scheduling.

As throughput increases, the stateful services may eventually become bottlenecks.

Potential bottlenecks include

- Redis queue throughput
- PostgreSQL metadata operations
- MinIO storage throughput
- network bandwidth between services

The scalability experiments evaluate how these components behave under increasing load and how overall throughput changes as additional worker instances are deployed.

The benchmark results show this behavior in practice. Horizontal worker scaling increases sustainable completed jobs per second up to the point where the worker layer is no longer the only bottleneck. At higher rates, queue lengths can remain low while p95 latency and submit errors increase, which indicates pressure on the centralized API, metadata, object storage, or network path.

---

# Future Extensions

The architecture intentionally leaves room for further improvements without requiring major structural changes.

Possible future extensions include

- additional image processing operations
- AI-based image processing algorithms
- dynamic workload classification
- priority-based scheduling
- automatic worker autoscaling
- distributed tracing
- metrics collection with Prometheus
- dashboard visualization with Grafana
- dead-letter queues for permanently failing jobs
- Kubernetes-based deployment
