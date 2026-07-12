# Scalability Evaluation

This document summarizes the scalability benchmark setup, the measured performance metric, the tested GCP deployment variants, and the main observations from the experiments.

For the detailed benchmark procedure, see [Benchmarking Methodology](benchmarking-methodology.md). For a concise final interpretation of the measured results, see [Scalability Findings](scalability-findings.md).

---

# Goal

The benchmark evaluates how the image processing pipeline behaves when worker capacity is scaled horizontally across multiple GCP virtual machines.

The expected scaling target is the asynchronous image processing layer. Workers are stateless and CPU-bound, while Redis, PostgreSQL, MinIO, and the API run on the main node.

The primary metric is:

```text
sustainable completed jobs per second
```

This is more useful than raw submitted requests per second because the system is asynchronous. A request can be accepted before the image has actually been processed.

A benchmark point is considered usable when:

- submitted jobs complete successfully
- failed jobs and benchmark errors are zero
- queue lengths do not grow without recovery
- p95 end-to-end latency remains within a reasonable range
- default and heavy queues drain after load stops

---

# Benchmark Workload

The main workload profile is:

```text
representative_mixed
```

It combines light, medium, and heavy image processing jobs. Heavy jobs include repeated blur or multi-step processing pipelines and are routed to the heavy queue.

The workload is generated with k6 through the load test runner. The benchmark runner records:

- submitted, completed, failed, and rejected jobs
- end-to-end latency and HTTP latency
- k6 execution metrics
- queue length timelines
- default/heavy queue drain time
- host CPU and memory
- per-node Docker container utilization
- API and worker logs

---

# Deployment Variants

Two groups of deployments were evaluated.

## Full 8 vCPU Nodes

These deployments use `e2-standard-8` for the main node and all worker nodes.

| Setup | Main Node | Worker Nodes | Total Workers |
| --- | --- | --- | --- |
| 1-node | `e2-standard-8`, `4D/4H` | none | `4D/4H` |
| 2-node | `e2-standard-8`, `4D/4H` | 1x `e2-standard-8`, `4D/4H` | `8D/8H` |
| 3-node | `e2-standard-8`, `4D/4H` | 2x `e2-standard-8`, `4D/4H` | `12D/12H` |
| 4-node | `e2-standard-8`, `4D/4H` | 3x `e2-standard-8`, `4D/4H` | `16D/16H` |

## Quota-Constrained Mixed Nodes

The GCP project had a global CPU quota of 32 vCPUs. A full 5-node `e2-standard-8` deployment would require 40 vCPUs, so the 5-node experiment uses smaller worker machines.

| Setup | Main Node | Worker Nodes | Total Workers |
| --- | --- | --- | --- |
| 1-node mixed | `e2-standard-8`, `4D/4H` | none | `4D/4H` |
| 2-node mixed | `e2-standard-8`, `4D/4H` | 1x `e2-standard-4`, `2D/2H` | `6D/6H` |
| 3-node mixed | `e2-standard-8`, `4D/4H` | 2x `e2-standard-4`, `2D/2H` | `8D/8H` |
| 4-node mixed | `e2-standard-8`, `4D/4H` | 3x `e2-standard-4`, `2D/2H` | `10D/10H` |
| 5-node mixed | `e2-standard-8`, `4D/4H` | 4x `e2-standard-4`, `2D/2H` | `12D/12H` |

---

# Results

## Full 8 vCPU Nodes

| Setup | Best Clean Offered Rate | Completed Jobs/s | Notes |
| --- | ---: | ---: | --- |
| 1-node | `1.5` | `1.304` | Clean 180s validation run |
| 2-node | `2.5` | `2.274` | Clean run, clear scaling |
| 3-node | `3.75` | `3.425` | Clean run, queues remained empty |
| 4-node | `3.75-4.0` tested near limit | `~3.5` | No clear sustainable improvement; submit errors appeared and bottleneck shifted |

The full 8 vCPU series scales well from 1 to 3 nodes. The 4-node deployment does not provide a proportional improvement. In the later validation sweep at 3.75 and 4.0 offered jobs/s, completed throughput stayed around 3.5 jobs/s, queues remained mostly low, and submit errors appeared. This indicates that the bottleneck shifts away from the worker layer.

## Quota-Constrained Mixed Nodes

| Setup | Best Clean Offered Rate | Completed Jobs/s | Notes |
| --- | ---: | ---: | --- |
| 1-node mixed | `1.5` | `1.304` | Same main-node baseline |
| 2-node mixed | `2.0` | `1.829` | Clean; `2.5` completed but with much higher p95 latency |
| 3-node mixed | `3.0` | `2.684` | Clean; `3.5` produced errors |
| 4-node mixed | `3.5` | `3.153` | Clean; `4.0` produced errors |
| 5-node mixed | `3.5` | `3.189` | Clean; little gain over 4 nodes |

The mixed series demonstrates a working 5-node deployment under the CPU quota. It still scales from 1 to 4 nodes, but it flattens at 5 nodes because the additional nodes have smaller machines and the centralized main-node services become increasingly important.

---

# Interpretation

The main scalability result is that horizontal worker scaling improves sustainable throughput until the worker layer is no longer the dominant bottleneck.

Observed behavior:

- From 1 to 3 full 8 vCPU nodes, completed jobs/s increases clearly.
- At 4 full 8 vCPU nodes, additional worker capacity does not translate into a proportional throughput gain.
- In the mixed 5-node setup, the system runs successfully, but the throughput gain over the 4-node mixed setup is small.
- At higher offered rates, the queues are often not the only bottleneck; p95 latency and submit errors indicate pressure on the API, object storage, metadata storage, or network path.

This is expected for the architecture: workers can be scaled horizontally, but the main node still hosts API, Redis, PostgreSQL, and MinIO.

---

# Bottleneck Indicators

The benchmark reports are used to distinguish worker bottlenecks from main-node or storage bottlenecks.

Worker bottleneck indicators:

- default or heavy queue grows during the test
- queue does not drain after load stops
- default or heavy worker CPU is high
- host CPU is high on worker nodes

Main-node or submission bottleneck indicators:

- queues stay small but HTTP p95 grows
- `error_timeline.csv` contains submit errors
- job submission fails even though worker queues are not saturated
- API, MinIO, or PostgreSQL utilization increases
- main node is busier than worker-only nodes

In the higher-rate 4-node and 5-node experiments, the latter pattern appears more frequently, suggesting that more worker nodes alone are no longer sufficient.

---

# Result Locations

The 8 vCPU experiment results were moved into:

```text
results/8cpu/
```

The mixed-node experiment results are stored in:

```text
results/sweeps/
results/loadtests/
```

Each sweep folder contains:

- `sweep_report.md`
- `sweep_results.csv`
- plots for throughput, latency, queue length, and worker CPU
- a `runs/` directory with full reports for each individual load test

The generated `results/` directory is ignored by Git to keep the repository small. The curated final result table is tracked in [Scalability Findings](scalability-findings.md) and [`scalability-results.csv`](scalability-results.csv).

---

# Limitations

- The benchmark uses a representative synthetic workload rather than production traffic.
- The GCP CPU quota prevented a full 5-node deployment with `e2-standard-8` on every node.
- Redis, PostgreSQL, MinIO, and the API remain centralized on the main node.
- At larger cluster sizes, the API submission path becomes part of the bottleneck: some HTTP submissions failed even though worker queues were not saturated.
- The stability threshold is based on operational criteria rather than a formal SLA.
- Some reported `Stable` values in sweep reports are conservative because completed jobs/s is calculated over the full observed period, including cooldown.

---

# Future Improvements

The next scalability improvements would target the bottlenecks that appear after worker scaling:

- run API replicas behind a load balancer
- move PostgreSQL to Cloud SQL or a larger dedicated machine
- move object storage to a managed object store
- use managed Redis or a larger Redis node
- add request-stage timing in the API for upload, metadata write, object storage, and enqueue latency
- add distributed tracing across API, storage, queue, and workers
