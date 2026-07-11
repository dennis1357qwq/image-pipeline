import argparse
import csv
import json
from pathlib import Path
from statistics import mean


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

    metrics = {
        **k6_summary.get("metrics", {}),
        **workload_summary.get("k6_metrics", {}),
    }

    completed_jobs = get_metric_count(metrics, "completed_jobs")
    submitted_jobs = get_metric_count(metrics, "submitted_jobs")
    failed_jobs = get_metric_count(metrics, "failed_jobs")
    rejected_jobs = get_metric_count(metrics, "rejected_jobs")

    throughput = get_metric_value(metrics, "completed_jobs", "rate", 0)

    analysis = {
        "run": {
            "profile": config.get("profile"),
            "rate": config.get("rate"),
            "duration": config.get("duration"),
            "environment": config.get("environment"),
            "setup": config.get("setup"),
            "worker_nodes": config.get("worker_nodes"),
            "workers_per_node": config.get("workers_per_node"),
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
        "workload": summarize_workload(workload_summary),
        "host": summarize_host_stats(host_rows),
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
