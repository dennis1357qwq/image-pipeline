import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from datetime import datetime, timedelta

def parse_duration_seconds(value: str) -> float:
    value = value.strip().lower()

    if value.endswith("ms"):
        return float(value[:-2]) / 1000
    if value.endswith("s"):
        return float(value[:-1])
    if value.endswith("m"):
        return float(value[:-1]) * 60

    raise ValueError(f"Unsupported duration: {value}")


def summarize_queue_drain(
    rows: list[dict],
    run_started_at: str | None,
    duration: str | None,
) -> dict:
    if not rows or not run_started_at or not duration:
        return {}

    submission_end = (
        datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
        + timedelta(seconds=parse_duration_seconds(duration))
    )

    rows = sorted(rows, key=lambda row: row["timestamp"])

    max_queue = 0
    first_nonzero_after_end = None
    drained_at = None

    for row in rows:
        timestamp = datetime.fromisoformat(
            row["timestamp"].replace("Z", "+00:00")
        )

        total_queue = (
            int(row.get("default_queue_length") or 0)
            + int(row.get("heavy_queue_length") or 0)
        )

        max_queue = max(max_queue, total_queue)

        if timestamp < submission_end:
            continue

        if total_queue > 0 and first_nonzero_after_end is None:
            first_nonzero_after_end = timestamp

        if first_nonzero_after_end is not None and total_queue == 0:
            drained_at = timestamp
            break

    if max_queue == 0:
        drain_seconds = 0.0
    elif first_nonzero_after_end is None:
        drain_seconds = 0.0
    elif drained_at is None:
        drain_seconds = None
    else:
        drain_seconds = round(
            (drained_at - submission_end).total_seconds(),
            2,
        )

    return {
        "max_queue_length": max_queue,
        "queue_drain_seconds": drain_seconds,
        "queue_drained": drained_at is not None or max_queue == 0,
    }

def parse_args():
    parser = argparse.ArgumentParser(description="Analyze benchmark run results.")
    parser.add_argument("run_dir", help="Path to a single benchmark run directory")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def get_metric_count(metrics: dict, name: str) -> int:
    return int(metrics.get(name, {}).get("values", {}).get("count", 0))


def get_metric_value(metrics: dict, name: str, value_name: str, default=None):
    return metrics.get(name, {}).get("values", {}).get(value_name, default)


def to_float(value, default=None):
    try:
        if value == "" or value is None:
            return default
        return float(value)
    except ValueError:
        return default

def summarize_host_io_by_node(rows: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}

    for row in rows:
        grouped.setdefault(row.get("node", "unknown"), []).append(row)

    summary = {}

    for node, node_rows in grouped.items():
        node_rows.sort(key=lambda row: row["timestamp"])

        first = node_rows[0]
        last = node_rows[-1]

        summary[node] = {
            "disk_read_bytes_delta": float(last["disk_read_bytes"]) - float(first["disk_read_bytes"]),
            "disk_write_bytes_delta": float(last["disk_write_bytes"]) - float(first["disk_write_bytes"]),
            "network_bytes_sent_delta": float(last["network_bytes_sent"]) - float(first["network_bytes_sent"]),
            "network_bytes_recv_delta": float(last["network_bytes_recv"]) - float(first["network_bytes_recv"]),
        }

    return summary

def summarize_host_stats(rows: list[dict]) -> dict:
    if not rows:
        return {}

    cpu_values = [to_float(row.get("cpu_percent")) for row in rows]
    memory_values = [to_float(row.get("memory_percent")) for row in rows]
    load_values = [to_float(row.get("load_1m")) for row in rows]

    cpu_values = [v for v in cpu_values if v is not None]
    memory_values = [v for v in memory_values if v is not None]
    load_values = [v for v in load_values if v is not None]

    return {
        "avg_cpu_percent": round(mean(cpu_values), 2) if cpu_values else None,
        "max_cpu_percent": round(max(cpu_values), 2) if cpu_values else None,
        "avg_memory_percent": round(mean(memory_values), 2) if memory_values else None,
        "max_memory_percent": round(max(memory_values), 2) if memory_values else None,
        "avg_load_1m": round(mean(load_values), 2) if load_values else None,
        "max_load_1m": round(max(load_values), 2) if load_values else None,
        "sample_count": len(rows),
    }


def summarize_docker_stats(rows: list[dict]) -> dict:
    containers: dict[str, dict[str, list[float]]] = {}

    for row in rows:
        container = row.get("container", "unknown")
        containers.setdefault(
            container,
            {
                "cpu": [],
                "memory": [],
            },
        )

        cpu = to_float(row.get("cpu_percent"))
        memory = to_float(row.get("memory_percent"))

        if cpu is not None:
            containers[container]["cpu"].append(cpu)

        if memory is not None:
            containers[container]["memory"].append(memory)

    summary = {}

    for container, values in containers.items():
        cpu_values = values["cpu"]
        memory_values = values["memory"]

        summary[container] = {
            "avg_cpu_percent": round(mean(cpu_values), 2) if cpu_values else None,
            "max_cpu_percent": round(max(cpu_values), 2) if cpu_values else None,
            "avg_memory_percent": round(mean(memory_values), 2) if memory_values else None,
            "max_memory_percent": round(max(memory_values), 2) if memory_values else None,
            "sample_count": max(len(cpu_values), len(memory_values)),
        }

    return summary


def group_rows_by_node(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}

    for row in rows:
        node_name = row.get("node") or "unknown"
        grouped.setdefault(node_name, []).append(row)

    return grouped


def summarize_host_stats_by_node(rows: list[dict]) -> dict:
    return {
        node_name: summarize_host_stats(node_rows)
        for node_name, node_rows in group_rows_by_node(rows).items()
    }


def summarize_docker_stats_by_node(rows: list[dict]) -> dict:
    return {
        node_name: summarize_docker_stats(node_rows)
        for node_name, node_rows in group_rows_by_node(rows).items()
    }


def count_worker_containers(rows: list[dict], worker_type: str) -> int:
    markers = (
        f"worker-{worker_type}",
        f"image-pipeline-worker-{worker_type}",
        f"docker-worker-{worker_type}",
    )

    containers = {
        row.get("container", "")
        for row in rows
        if any(marker in row.get("container", "") for marker in markers)
    }

    return len(containers)


def summarize_workload(workload_summary: dict) -> dict:
    submitted = workload_summary.get("submitted_by_task", {})
    completed = workload_summary.get("completed_by_task", {})

    total_submitted = sum(submitted.values()) if submitted else 0
    total_completed = sum(completed.values()) if completed else 0

    task_distribution = {}
    def task_label(task_name: str) -> str:
        labels = {
            "light_grayscale_small": "Grayscale S",
            "light_rotate_small": "Rotate S",
            "light_region_blur_medium": "Region Blur M",
            "medium_thumbnail_medium": "Thumbnail M",
            "medium_edge_detect_medium": "Edge Detect M",
            "heavy_blur_repeat_medium": "Blur Repeat M",
            "heavy_mixed_pipeline_medium": "Mixed Heavy M",
        }
        return labels.get(task_name, task_name)

    for task_name, count in submitted.items():
        percentage = (count / total_submitted * 100) if total_submitted else 0

        task_distribution[task_name] = {
            "submitted": count,
            "completed": completed.get(task_name, 0),
            "submitted_percent": round(percentage, 2),
            "label": task_label(task_name),
        }

    return {
        "total_submitted": total_submitted,
        "total_completed": total_completed,
        "task_distribution": task_distribution,
    }


def analyze_run(run_dir: Path) -> Path:
    config = load_json(run_dir / "config.json")
    k6_summary = load_json(run_dir / "k6_summary.json")
    workload_summary = load_json(run_dir / "workload_summary.json")
    docker_rows = load_csv(run_dir / "docker_stats.csv")
    host_rows = load_csv(run_dir / "host_stats.csv")
    queue_rows = load_csv(run_dir / "queue_stats.csv")

    metrics = {
        **k6_summary.get("metrics", {}),
        **workload_summary.get("k6_metrics", {}),
    }

    completed_jobs = get_metric_count(metrics, "completed_jobs")
    submitted_jobs = get_metric_count(metrics, "submitted_jobs")
    failed_jobs = get_metric_count(metrics, "failed_jobs")
    rejected_jobs = get_metric_count(metrics, "rejected_jobs")

    throughput = get_metric_value(metrics, "completed_jobs", "rate", 0)
    main_node_default_workers = config.get("main_node_default_workers")
    main_node_heavy_workers = config.get("main_node_heavy_workers")
    worker_node_default_workers = config.get("worker_node_default_workers")
    worker_node_heavy_workers = config.get("worker_node_heavy_workers")
    default_workers = config.get("default_workers")
    heavy_workers = config.get("heavy_workers")

    if default_workers is None:
        default_workers = count_worker_containers(docker_rows, "default")

    if heavy_workers is None:
        heavy_workers = count_worker_containers(docker_rows, "heavy")

    total_workers = config.get("total_workers")

    if total_workers is None:
        total_workers = default_workers + heavy_workers

    worker_nodes = config.get("worker_nodes") or 0

    if config.get("environment") == "local":
        worker_nodes = 0

    if main_node_default_workers is None:
        main_node_default_workers = (
            default_workers if worker_nodes == 0 else None
        )

    if main_node_heavy_workers is None:
        main_node_heavy_workers = (
            heavy_workers if worker_nodes == 0 else None
        )

    if worker_node_default_workers is None:
        worker_node_default_workers = 0 if worker_nodes == 0 else None

    if worker_node_heavy_workers is None:
        worker_node_heavy_workers = 0 if worker_nodes == 0 else None

    analysis = {
        "run": {
            "profile": config.get("profile"),
            "rate": config.get("rate"),
            "duration": config.get("duration"),
            "environment": config.get("environment"),
            "setup": config.get("setup"),
            "worker_nodes": worker_nodes,
            "workers_per_node": config.get("workers_per_node"),
            "main_node_default_workers": main_node_default_workers,
            "main_node_heavy_workers": main_node_heavy_workers,
            "worker_node_default_workers": worker_node_default_workers,
            "worker_node_heavy_workers": worker_node_heavy_workers,
            "default_workers": default_workers,
            "heavy_workers": heavy_workers,
            "total_workers": total_workers,
            "default_worker_containers": config.get("default_worker_containers", []),
            "heavy_worker_containers": config.get("heavy_worker_containers", []),
            "notes": config.get("notes"),
        },
        "throughput": {
            "submitted_jobs": submitted_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "rejected_jobs": rejected_jobs,
            "completed_jobs_per_second": round(throughput, 3) if throughput is not None else None,
        },
        "latency": {
            "end_to_end_avg_ms": get_metric_value(metrics, "end_to_end_time_ms", "avg"),
            "end_to_end_p95_ms": get_metric_value(metrics, "end_to_end_time_ms", "p(95)"),
            "http_req_avg_ms": get_metric_value(metrics, "http_req_duration", "avg"),
            "http_req_p95_ms": get_metric_value(metrics, "http_req_duration", "p(95)"),
        },
        "queue": summarize_queue_drain(
            queue_rows,
            config.get("run_started_at"),
            config.get("duration"),
        ),
        "workload": summarize_workload(workload_summary),
        "host": summarize_host_stats(host_rows),
        "host_io_by_node": summarize_host_io_by_node(host_rows),
        "host_by_node": summarize_host_stats_by_node(host_rows),
        "docker": summarize_docker_stats(docker_rows),
        "docker_by_node": summarize_docker_stats_by_node(docker_rows),
    }

    output_path = run_dir / "analysis_summary.json"
    output_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return output_path


def main():
    args = parse_args()
    output_path = analyze_run(Path(args.run_dir))
    print(f"Analysis written to: {output_path}")


if __name__ == "__main__":
    main()
