# Benchmarking Methodology

This document describes the testing logic, experimental setup, and benchmark workflow used for the scalability evaluation.

---

# Goal

The benchmark measures how the image processing pipeline scales when worker capacity is increased across multiple GCP virtual machines.

The main question is:

```text
How many image processing jobs per second can the system complete sustainably?
```

The benchmark focuses on completed jobs rather than accepted HTTP requests because job processing is asynchronous. The API can accept a job before the image has actually been processed by a worker.

---

# Primary Metric

The primary metric is:

```text
sustainable completed jobs per second
```

A point is considered sustainable when:

- jobs complete successfully
- failed jobs and submit errors are zero or negligible
- queue lengths do not grow without recovery
- default and heavy queues drain after load stops
- p95 end-to-end latency remains within a reasonable range
- CPU utilization is high enough to indicate useful work but not completely saturated

The offered request rate is used as the input load. Completed jobs/s is used as the output performance metric.

---

# Workload Profile

The main benchmark profile is:

```text
representative_mixed
```

It contains a weighted mix of light, medium, and heavy image processing operations. This profile was chosen because it is closer to realistic usage than testing only one operation type.

The workload includes:

- small light operations such as grayscale and rotate
- medium operations such as thumbnail generation and edge detection
- heavy operations such as repeated blur and multi-step pipelines

Heavy jobs are routed to the heavy worker queue. Other jobs are routed to the default worker queue.

---

# System Under Test

Each deployment has one main node and zero or more worker-only nodes.

The main node runs:

- FastAPI
- Redis
- PostgreSQL
- MinIO
- optional default workers
- optional heavy workers

Worker-only nodes run:

- default workers
- heavy workers

Workers are stateless and connect to Redis, PostgreSQL, and MinIO on the main node through the internal GCP network.

---

# Benchmark Tools

The load test stack consists of:

- `k6` for generating job submission load
- `cluster_runner.py` for one benchmark run against a deployment
- `sweep_runner.py` for running several offered rates against the same deployment
- remote monitoring scripts for host, Docker, and queue metrics
- report generators for Markdown, CSV, and plots

The runner collects:

- submitted, completed, failed, and rejected jobs
- HTTP latency
- end-to-end job latency
- k6 iterations and dropped iterations
- default and heavy queue length
- queue drain time
- host CPU and memory
- container CPU and memory
- error and timeout timeline

---

# Single Run Procedure

A single benchmark run follows this sequence:

1. Read the cluster config.
2. Check API health.
3. Check non-interactive SSH access to all nodes.
4. Clean previous benchmark state.
5. Start remote monitors on all nodes.
6. Collect warmup/baseline metrics.
7. Run the k6 workload for the configured duration and rate.
8. Poll submitted jobs until completion, failure, or timeout.
9. Collect cooldown metrics.
10. Stop monitors and download metrics.
11. Generate analysis files, plots, and a Markdown report.

The output directory name encodes the deployment size, worker counts, offered rate, duration, workload profile, timestamp, and run id.

---

# Sweep Procedure

A sweep runs multiple single benchmarks against the same deployment with different offered rates.

Example:

```text
rates = 2.5, 3.0, 3.5
duration = 120s
profile = representative_mixed
```

The sweep is used to find the highest usable rate for a deployment. Each rate produces a normal single-run report. The sweep then summarizes the results in:

- `sweep_results.csv`
- `sweep_report.md`
- throughput vs offered rate plot
- latency vs offered rate plot
- queue vs offered rate plot
- worker CPU vs offered rate plot

---

# Warmup, Duration, and Cooldown

The benchmark uses three timing phases:

## Warmup

Warmup collects baseline metrics before load starts. It helps distinguish idle system behavior from load-induced behavior.

## Duration

Duration is the active load phase. During this phase, k6 submits jobs at the configured offered rate.

## Cooldown

Cooldown continues monitoring after load stops. This is important because the API is asynchronous: jobs can remain queued or processing after k6 stops submitting new work.

Cooldown is used to observe whether queues recover and drain. A run where queues keep growing or do not drain is not considered sustainably stable.

---

# Worker Configuration Search

Before scaling to multiple nodes, worker counts were tuned on a single 8 vCPU node.

The search compared different default/heavy worker ratios. The target was:

- high completed jobs/s
- recoverable default and heavy queues
- no failed jobs
- no permanent queue growth
- high but not overloaded CPU utilization

For the `representative_mixed` workload, the selected main-node baseline was:

```text
4 default workers + 4 heavy workers
```

This became the reference configuration for later multi-node tests.

---

# Scaling Experiment Design

Two deployment families were tested.

## Full 8 vCPU Series

Each node uses `e2-standard-8`:

- 1-node
- 2-node
- 3-node
- 4-node

This series tests horizontal scaling with equal machine sizes.

## Mixed Node Series

The main node uses `e2-standard-8`, while worker nodes use `e2-standard-4`:

- 1-node
- 2-node
- 3-node
- 4-node
- 5-node

This series was used because the GCP project had a 32 vCPU global quota. A full 5-node `e2-standard-8` deployment would require 40 vCPUs.

---

# Bottleneck Analysis Logic

The benchmark distinguishes between worker bottlenecks and main-node/submission bottlenecks.

## Worker Bottleneck Indicators

- default or heavy queue grows during the test
- queue does not drain after load stops
- worker CPU is high
- adding workers increases completed jobs/s

## Main-Node or Submission Bottleneck Indicators

- queues stay low but throughput flattens
- HTTP submit errors appear
- HTTP p95 or end-to-end p95 increases
- worker CPU is not saturated
- adding worker nodes does not meaningfully increase completed jobs/s

At larger cluster sizes, the observed behavior matched the second pattern more often. This suggests that the bottleneck shifts toward the API submission path, MinIO, PostgreSQL, Redis, or internal network transfer.

---

# Result Interpretation

The most important result is not the highest offered rate. The important result is the highest rate the system can process sustainably.

For each deployment, the benchmark asks:

```text
At what offered rate do completed jobs/s stop increasing cleanly?
```

If completed jobs/s flattens while queues stay low and submit errors appear, the system is no longer worker-limited. At that point, adding more worker nodes is expected to provide diminishing returns unless the shared services are also scaled or moved to dedicated infrastructure.

---

# Reproducibility

Terraform deployment profiles are stored in:

```text
infra/terraform/gcp-benchmark/deployments/
```

Benchmark runner code is stored in:

```text
benchmark/loadtest_runner/
```

The curated final result table is stored in:

```text
docs/scalability-results.csv
```

Raw benchmark output is generated under:

```text
results/
```

The `results/` directory is ignored by Git because it contains large generated output such as plots, CSV files, JSON summaries, and per-run reports.
