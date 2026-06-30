# Image Processing Operations

This document describes the processing pipeline supported by the Image Processing Pipeline project, the available image operations, their parameters, and an initial estimate of their computational costs.

---

# Processing Pipeline

Each submitted job consists of an ordered list of processing steps.

Each processing step contains

```json
{
    "operation": "...",
    "parameters": {
        ...
    }
}
```

The worker executes every processing step sequentially on the same image.

---

# Shared Parameters

Several operations support additional optional parameters.

## repeat

```text
Default: 1
```

Repeats the operation multiple times before continuing with the next pipeline step.

This parameter is primarily intended to generate computationally expensive workloads for scalability experiments.

Example:

```json
{
  "operation": "blur",
  "parameters": {
    "radius": 8,
    "repeat": 10
  }
}
```

---

## region

Limits processing to a rectangular image region.

```json
{
  "region": {
    "x": 100,
    "y": 100,
    "width": 400,
    "height": 300
  }
}
```

Only this part of the image is modified.

---

# Supported Operations

## Grayscale

Converts the image to grayscale.

### Parameters

None

---

## Thumbnail

Creates a thumbnail while preserving the aspect ratio.

### Parameters

| Parameter | Default |
| --------- | ------- |
| width     | 300     |
| height    | 300     |

---

## Blur

Applies a Gaussian blur.

### Parameters

| Parameter | Default    |
| --------- | ---------- |
| radius    | 4          |
| repeat    | 1          |
| region    | Full image |

---

## Rotate

Rotates the image.

### Parameters

| Parameter | Default |
| --------- | ------- |
| angle     | 90°     |

---

## Sharpen

Increases image sharpness.

### Parameters

| Parameter | Default    |
| --------- | ---------- |
| factor    | 2.0        |
| repeat    | 1          |
| region    | Full image |

---

## Contrast

Adjusts image contrast.

### Parameters

| Parameter | Default    |
| --------- | ---------- |
| factor    | 2.0        |
| repeat    | 1          |
| region    | Full image |

---

## Edge Detection

Detects image edges.

### Parameters

None

---

## Emboss

Applies an emboss filter.

### Parameters

None

---

# Initial Performance Baseline

The following values were measured using the local benchmark utility.

Environment:

- Local development machine
- Input image: 1932 × 1008 PNG
- 20 benchmark iterations
- 3 warm-up iterations

The values below are intended as relative computational costs rather than absolute performance guarantees.

| Operation          | Typical Runtime | Relative Cost |
| ------------------ | --------------: | ------------- |
| Rotate             |         ~2–3 ms | Low           |
| Grayscale          |         ~3–4 ms | Low           |
| Region Blur        |         ~4–5 ms | Low           |
| Thumbnail          |          ~15 ms | Medium        |
| Emboss             |          ~15 ms | Medium        |
| Contrast           |          ~16 ms | Medium        |
| Edge Detection     |          ~22 ms | Medium        |
| Sharpen            |          ~24 ms | Medium        |
| Blur               |          ~35 ms | Medium        |
| Mixed Pipeline     |         ~116 ms | High          |
| Blur (`repeat=10`) |         ~350 ms | High          |

---

# Benchmark Methodology

Measurements were collected using the benchmark utility located in

```text
scripts/benchmark_operations.py
```

Each benchmark consists of

- warm-up iterations
- randomized execution order
- repeated measurements
- wall-clock time
- CPU execution time

Benchmark results are intentionally stored separately from the repository because they depend on the execution environment.

The values shown in this document represent an initial local baseline. Final benchmark results will be collected on the target cloud deployment during scalability evaluation.
