import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from benchmark.loadtest_runner.analyze_results import parse_duration_seconds
from benchmark.loadtest_runner.node_config import load_cluster_config
from benchmark.loadtest_runner.run_naming import timestamp_for_run_name

def parse_args():
    parser = argparse.ArgumentParser(description="Run a benchmark rate sweep.")
    parser.add_argument("--mode", choices=["local", "cluster"], required=True)
    parser.add_argument("--rates", required=True, help="Comma-separated rates")
    parser.add_argument("--duration", default="60s")
    parser.add_argument("--profile", default="representative_mixed")
    parser.add_argument("--results-dir", default="results/sweeps")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--cluster-config")
    parser.add_argument("--poll-result", default="true")
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--poll-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--monitor-interval-seconds", type=float, default=1.0)
    parser.add_argument("--monitor-warmup-seconds", type=float, default=3.0)
    parser.add_argument("--monitor-cooldown-seconds", type=float, default=3.0)
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument(
        "--remote-python",
        default="benchmark/venv/bin/python3",
        help="Python executable relative to the project directory on each VM.",
    )
    parser.add_argument("--main-node-default-workers", type=int, default=0)
    parser.add_argument("--main-node-heavy-workers", type=int, default=0)
    parser.add_argument("--worker-node-default-workers", type=int, default=0)
    parser.add_argument("--worker-node-heavy-workers", type=int, default=0)
    parser.add_argument(
        "--cleanup-before-run",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args()


def load_analysis(run_dir: Path) -> dict:
    path = run_dir / "analysis_summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_run_config(run_dir: Path) -> dict:
    path = run_dir / "config.json"

    if not path.exists():
        return {}

    return json.loads(path.read_text(encoding="utf-8"))


def find_latest_run(results_dir: Path) -> Path:
    return (results_dir / "latest").resolve()


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def calculate_drain_seconds(
    rows: list[dict],
    queue_fields: tuple[str, ...],
    run_started_at: str | None,
    duration: str | None,
) -> float | None:
    if not rows or not run_started_at or not duration:
        return None

    submission_end = (
        datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
        + timedelta(seconds=parse_duration_seconds(duration))
    )

    first_nonzero_after_end = None

    for row in sorted(rows, key=lambda item: item["timestamp"]):
        timestamp = datetime.fromisoformat(
            row["timestamp"].replace("Z", "+00:00")
        )

        if timestamp < submission_end:
            continue

        queue_length = sum(
            int(row.get(queue_field) or 0)
            for queue_field in queue_fields
        )

        if queue_length > 0 and first_nonzero_after_end is None:
            first_nonzero_after_end = timestamp

        if first_nonzero_after_end is not None and queue_length == 0:
            return round((timestamp - submission_end).total_seconds(), 2)

    return 0.0 if first_nonzero_after_end is None else None


def queue_metrics(run_dir: Path, config: dict) -> dict:
    path = run_dir / "queue_stats.csv"
    rows = read_csv_rows(path)

    if not rows:
        return {
            "max_queue_length": 0,
            "max_default_queue_length": 0,
            "max_heavy_queue_length": 0,
            "queue_drain_seconds": None,
            "default_queue_drain_seconds": None,
            "heavy_queue_drain_seconds": None,
        }

    max_default = max(
        int(row.get("default_queue_length") or 0)
        for row in rows
    )
    max_heavy = max(
        int(row.get("heavy_queue_length") or 0)
        for row in rows
    )
    max_total = max(
        int(row.get("default_queue_length") or 0)
        + int(row.get("heavy_queue_length") or 0)
        for row in rows
    )

    run_started_at = config.get("run_started_at")
    duration = config.get("duration")

    return {
        "max_queue_length": max_total,
        "max_default_queue_length": max_default,
        "max_heavy_queue_length": max_heavy,
        "queue_drain_seconds": calculate_drain_seconds(
            rows,
            ("default_queue_length", "heavy_queue_length"),
            run_started_at,
            duration,
        ),
        "default_queue_drain_seconds": calculate_drain_seconds(
            rows,
            ("default_queue_length",),
            run_started_at,
            duration,
        ),
        "heavy_queue_drain_seconds": calculate_drain_seconds(
            rows,
            ("heavy_queue_length",),
            run_started_at,
            duration,
        ),
    }


def worker_cpu_metrics(run_dir: Path, worker_type: str) -> dict:
    rows = read_csv_rows(run_dir / "docker_stats.csv")
    marker = f"worker-{worker_type}"
    cpu_values = [
        float(row["cpu_percent"])
        for row in rows
        if marker in row.get("container", "")
        and row.get("cpu_percent") not in (None, "")
    ]

    return {
        f"avg_{worker_type}_worker_cpu_percent": (
            round(mean(cpu_values), 2) if cpu_values else None
        ),
        f"max_{worker_type}_worker_cpu_percent": (
            round(max(cpu_values), 2) if cpu_values else None
        ),
    }


def error_count(run_dir: Path) -> int:
    path = run_dir / "error_timeline.csv"

    if not path.exists():
        return 0

    with path.open("r", encoding="utf-8") as file:
        return sum(1 for _ in csv.DictReader(file))


def main():
    args = parse_args()
    rates = [float(value) for value in args.rates.split(",")]

    timestamp = timestamp_for_run_name()
    rate_label = "-".join(
        str(int(rate)) if rate.is_integer() else str(rate).replace(".", "p")
        for rate in rates
    )
    environment_label = "gcp" if args.mode == "cluster" else "local"
    total_nodes = 1
    worker_node_count = 0

    if args.mode == "cluster":
        if not args.cluster_config:
            raise ValueError("--cluster-config is required in cluster mode")

        total_nodes = len(load_cluster_config(Path(args.cluster_config)).nodes)
        worker_node_count = max(total_nodes - 1, 0)

    default_workers = (
        args.main_node_default_workers
        + worker_node_count * args.worker_node_default_workers
    )
    heavy_workers = (
        args.main_node_heavy_workers
        + worker_node_count * args.worker_node_heavy_workers
    )
    sweep_name = (
        f"sweep-{total_nodes}-node-{environment_label}-"
        f"{heavy_workers}h-{default_workers}d-worker-"
        f"{rate_label}rps-{args.duration}-{args.profile}-{timestamp}"
    )
    sweep_dir = Path(args.results_dir) / sweep_name
    sweep_dir.mkdir(parents=True, exist_ok=True)
    sweep_runs_dir = sweep_dir / "runs"
    sweep_runs_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for rate in rates:
        print(f"Running rate {rate} jobs/s...")

        if args.mode == "local":
            command = [
                sys.executable,
                "-m",
                "benchmark.loadtest_runner.run_benchmark",
                "--base-url",
                args.base_url,
                "--profile",
                args.profile,
                "--rate",
                str(rate),
                "--duration",
                args.duration,
                "--poll-result",
                args.poll_result,
                "--poll-interval-seconds",
                str(args.poll_interval_seconds),
                "--poll-timeout-seconds",
                str(args.poll_timeout_seconds),
                "--monitor-interval-seconds",
                str(args.monitor_interval_seconds),
                "--redis-url",
                args.redis_url,
                "--results-dir",
                str(sweep_runs_dir),
            ]

            if not args.cleanup_before_run:
                command.append("--no-cleanup-before-run")
        else:
            command = [
                sys.executable,
                "-m",
                "benchmark.loadtest_runner.cluster_runner",
                "--config",
                args.cluster_config,
                "--profile",
                args.profile,
                "--rate",
                str(rate),
                "--duration",
                args.duration,
                "--poll-result",
                args.poll_result,
                "--poll-interval-seconds",
                str(args.poll_interval_seconds),
                "--poll-timeout-seconds",
                str(args.poll_timeout_seconds),
                "--monitor-interval-seconds",
                str(args.monitor_interval_seconds),
                "--monitor-warmup-seconds",
                str(args.monitor_warmup_seconds),
                "--monitor-cooldown-seconds",
                str(args.monitor_cooldown_seconds),
                "--redis-url",
                args.redis_url,
                "--remote-python",
                args.remote_python,
                "--main-node-default-workers",
                str(args.main_node_default_workers),
                "--main-node-heavy-workers",
                str(args.main_node_heavy_workers),
                "--worker-node-default-workers",
                str(args.worker_node_default_workers),
                "--worker-node-heavy-workers",
                str(args.worker_node_heavy_workers),
                "--results-dir",
                str(sweep_runs_dir),
            ]

            if not args.cleanup_before_run:
                command.append("--no-cleanup-before-run")

        result = subprocess.run(command)

        if result.returncode != 0:
            raise SystemExit(result.returncode)

        run_dir = find_latest_run(sweep_runs_dir)
        analysis = load_analysis(run_dir)
        config = load_run_config(run_dir)

        throughput = analysis.get("throughput", {})
        latency = analysis.get("latency", {})
        host = analysis.get("host", {})
        queues = queue_metrics(run_dir, config)
        default_worker_cpu = worker_cpu_metrics(run_dir, "default")
        heavy_worker_cpu = worker_cpu_metrics(run_dir, "heavy")

        rows.append(
            {
                "rate": rate,
                "submitted_jobs": throughput.get("submitted_jobs"),
                "completed_jobs": throughput.get("completed_jobs"),
                "completed_jobs_per_second": throughput.get(
                    "completed_jobs_per_second"
                ),
                "failed_jobs": throughput.get("failed_jobs"),
                "rejected_jobs": throughput.get("rejected_jobs"),
                "end_to_end_p95_ms": latency.get("end_to_end_p95_ms"),
                "avg_cpu_percent": host.get("avg_cpu_percent"),
                "max_cpu_percent": host.get("max_cpu_percent"),
                "max_queue_length": queues["max_queue_length"],
                "max_default_queue_length": queues["max_default_queue_length"],
                "max_heavy_queue_length": queues["max_heavy_queue_length"],
                "queue_drain_seconds": queues["queue_drain_seconds"],
                "default_queue_drain_seconds": queues[
                    "default_queue_drain_seconds"
                ],
                "heavy_queue_drain_seconds": queues[
                    "heavy_queue_drain_seconds"
                ],
                **default_worker_cpu,
                **heavy_worker_cpu,
                "error_count": error_count(run_dir),
                "run_dir": str(run_dir),
            }
        )

    output_path = sweep_dir / "sweep_results.csv"

    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Sweep results: {output_path}")

    from benchmark.loadtest_runner.sweep_report import generate_sweep_report

    generate_sweep_report(sweep_dir)


if __name__ == "__main__":
    main()
