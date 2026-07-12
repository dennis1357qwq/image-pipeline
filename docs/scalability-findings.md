# Scalability Findings

This report summarizes the final scalability findings for the image processing pipeline. It is intended to make the benchmark outcome understandable without the presentation slides.

---

# Executive Summary

The system scales horizontally while image processing workers are the dominant bottleneck. Throughput improves clearly when moving from one node to two and three nodes. At larger cluster sizes, throughput starts to flatten even though worker queues are often not saturated. This indicates that the bottleneck shifts from CPU-bound image processing workers to the centralized submission path and shared main-node services.

The primary benchmark metric is:

```text
sustainable completed jobs per second
```

This metric is used instead of raw offered requests per second because the API is asynchronous: accepting a job does not mean that the image was already processed.

---

# Stability Criteria

A run was treated as a useful stable point when:

- jobs completed successfully
- failed jobs and benchmark errors were zero or negligible
- default and heavy queues did not grow without recovery
- queues drained after load stopped
- p95 end-to-end latency stayed within a reasonable range
- CPU utilization was high enough to indicate useful work but not completely overloaded

This means that the final throughput values are conservative. They represent usable processing capacity rather than the highest offered load that the API could briefly accept.

---

# Worker Configuration Search

Before comparing multi-node deployments, the single-node setup was tuned to find a reasonable default/heavy worker mix.

The goal was to maximize completed jobs/s while keeping queues recoverable and avoiding failed jobs. Because the `representative_mixed` workload contains light, medium, and heavy operations, both worker pools matter. Heavy jobs are much more expensive, so too few heavy workers quickly causes the heavy queue to accumulate. Too many workers, however, can oversubscribe CPU and increase contention.

The best single-node configuration for the 8 vCPU main node was:

```text
4 default workers + 4 heavy workers
```

This configuration was then used as the main-node baseline for the scaling experiments.

---

# Deployment Series

Two deployment series were measured.

## Full 8 vCPU Nodes

All nodes use `e2-standard-8`.

| Cluster Size | Main Node | Worker Nodes | Total Worker Processes |
| ---: | --- | --- | --- |
| 1 | `e2-standard-8`, `4D/4H` | none | `4D/4H` |
| 2 | `e2-standard-8`, `4D/4H` | 1x `e2-standard-8`, `4D/4H` | `8D/8H` |
| 3 | `e2-standard-8`, `4D/4H` | 2x `e2-standard-8`, `4D/4H` | `12D/12H` |
| 4 | `e2-standard-8`, `4D/4H` | 3x `e2-standard-8`, `4D/4H` | `16D/16H` |

## Mixed Nodes

The GCP project had a global CPU quota of 32 vCPUs. A full 5-node `e2-standard-8` deployment would require 40 vCPUs, so a mixed series was used to evaluate a 5-node topology under the quota.

| Cluster Size | Main Node | Worker Nodes | Total Worker Processes |
| ---: | --- | --- | --- |
| 1 | `e2-standard-8`, `4D/4H` | none | `4D/4H` |
| 2 | `e2-standard-8`, `4D/4H` | 1x `e2-standard-4`, `2D/2H` | `6D/6H` |
| 3 | `e2-standard-8`, `4D/4H` | 2x `e2-standard-4`, `2D/2H` | `8D/8H` |
| 4 | `e2-standard-8`, `4D/4H` | 3x `e2-standard-4`, `2D/2H` | `10D/10H` |
| 5 | `e2-standard-8`, `4D/4H` | 4x `e2-standard-4`, `2D/2H` | `12D/12H` |

---

# Final Throughput Summary

The following table summarizes the final stable throughput values used for the presentation.

| Cluster Size | Full 8 vCPU Nodes | Mixed: 8 vCPU Main / 4 vCPU Workers |
| ---: | ---: | ---: |
| 1 | `1.304` jobs/s | `1.304` jobs/s |
| 2 | `2.274` jobs/s | `1.829` jobs/s |
| 3 | `3.425` jobs/s | `2.684` jobs/s |
| 4 | `~3.5` jobs/s | `3.153` jobs/s |
| 5 | not possible under 32 vCPU quota | `3.189` jobs/s |

The full 8 vCPU series shows strong scaling from 1 to 3 nodes. The 4-node result reaches roughly 3.5 completed jobs/s, but does not improve proportionally. The mixed series continues to validate a 5-node deployment, but the 5-node throughput is only slightly higher than the 4-node mixed result.

A compact machine-readable version of these selected result points is stored in [`scalability-results.csv`](scalability-results.csv). The full raw benchmark output remains local under `results/` because it contains many generated CSV, JSON, PNG, and per-run files.

---

# Main Findings

## 1. Worker Scaling Helps Initially

From 1 to 3 full 8 vCPU nodes, throughput increases clearly:

```text
1 node:  1.304 jobs/s
2 nodes: 2.274 jobs/s
3 nodes: 3.425 jobs/s
```

This confirms that the image processing layer benefits from horizontal worker scaling.

## 2. Scaling Flattens at Larger Cluster Sizes

At 4 full 8 vCPU nodes, the system does not show a proportional gain. The later validation sweep around the limit measured approximately:

```text
3.75 offered jobs/s -> 3.525 completed jobs/s
4.00 offered jobs/s -> 3.469 completed jobs/s
```

This suggests that the system is close to a throughput plateau for the current architecture.

## 3. The Bottleneck Moves Away from Workers

In the larger-cluster experiments, worker queues often stayed low while latency increased and submit errors appeared.

This is an important pattern:

- if queues grow, worker processing is too slow
- if queues stay low but HTTP submissions fail or become slow, the bottleneck is before or during job intake

The likely bottleneck path is:

```text
k6/client -> API -> image upload -> MinIO -> PostgreSQL metadata insert -> Redis enqueue
```

The result is that adding more workers no longer helps as much because the shared main-node services and submission path become limiting.

## 4. The 5-Node Mixed Setup Works but Does Not Add Much Throughput

The 5-node mixed deployment validates that the system can run across five VMs under the CPU quota. However, throughput only improves slightly over the 4-node mixed deployment:

```text
4-node mixed: 3.153 jobs/s
5-node mixed: 3.189 jobs/s
```

This supports the same bottleneck interpretation: once the shared services dominate, extra worker nodes provide diminishing returns.

---

# Bottleneck Interpretation

The benchmark evidence points to a shift in bottlenecks as the system scales.

Early scaling phase:

- workers are busy
- queues indicate whether default or heavy workers are under-provisioned
- adding worker capacity improves throughput

Later scaling phase:

- queues remain mostly low
- worker CPU is not fully saturated
- submit errors appear
- p95 latency increases
- completed jobs/s plateaus

This later behavior suggests pressure on one or more centralized components:

- API submission path
- MinIO object storage throughput
- PostgreSQL metadata writes
- Redis enqueue/dequeue traffic
- network transfer between API, workers, and storage

The strongest practical conclusion is that scaling workers alone is not enough beyond approximately 3 to 4 nodes for this architecture.

---

# Limitations

- The workload is synthetic but representative, not production traffic.
- The main workload is `representative_mixed`; different task mixes could produce different optimal worker ratios.
- API, Redis, PostgreSQL, and MinIO are centralized on the main node.
- The full 5-node 8 vCPU experiment was blocked by a 32 vCPU global quota.
- Stability was judged using operational benchmark indicators rather than a formal service-level objective.

---

# Recommended Next Steps

The next improvements should target the shared bottleneck path rather than only adding workers:

- add detailed API stage timing for upload, database insert, object storage write, and Redis enqueue
- move PostgreSQL to a managed or dedicated database instance
- move object storage to a managed object store
- use managed Redis or a larger dedicated Redis node
- run multiple API replicas behind a load balancer
- add distributed tracing across API, queue, storage, and workers

---

# Evidence

The repository keeps the final interpreted result table in this document and in [`scalability-results.csv`](scalability-results.csv). The raw generated benchmark output is intentionally not tracked in Git because it contains many generated CSV, JSON, PNG, and per-run files.

The local raw result folders used for this report were:

```text
results/8cpu/
results/sweeps/
results/loadtests/
```

For reproducibility, the Terraform deployment profiles and benchmark runner commands are tracked in the repository, so the same experiments can be re-run.
