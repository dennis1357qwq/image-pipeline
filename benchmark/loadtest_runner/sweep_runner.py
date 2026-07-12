import argparse
import csv
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from benchmark.loadtest_runner.sweep_report import generate_sweep_report

def parse_args():
    parser = argparse.ArgumentParser(description="Run a benchmark rate sweep.")
    parser.add_argument("--mode", choices=["local", "cluster"], required=True)
    parser.add_argument("--rates", required=True, help="Comma-separated rates")
    parser.add_argument("--duration", default="60s")
    parser.add_argument("--profile", default="representative_mixed")
    parser.add_argument("--results-dir", default="results/sweeps")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--cluster-config")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
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


def find_latest_run() -> Path:
    return Path("results/loadtests/latest").resolve()


def max_queue(run_dir: Path) -> int:
    path = run_dir / "queue_stats.csv"

    if not path.exists():
        return 0

    maximum = 0

    with path.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            total = (
                int(row.get("default_queue_length") or 0)
                + int(row.get("heavy_queue_length") or 0)
            )
            maximum = max(maximum, total)

    return maximum


def error_count(run_dir: Path) -> int:
    path = run_dir / "error_timeline.csv"

    if not path.exists():
        return 0

    with path.open("r", encoding="utf-8") as file:
        return sum(1 for _ in csv.DictReader(file))


def main():
    args = parse_args()
    rates = [float(value) for value in args.rates.split(",")]

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sweep_dir = Path(args.results_dir) / f"{timestamp}_{args.profile}"
    sweep_dir.mkdir(parents=True, exist_ok=True)

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
                "true",
            ]

            if not args.cleanup_before_run:
                command.append("--no-cleanup-before-run")
        else:
            if not args.cluster_config:
                raise ValueError("--cluster-config is required in cluster mode")

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
                "--redis-url",
                args.redis_url,
                "--main-node-default-workers",
                str(args.main_node_default_workers),
                "--main-node-heavy-workers",
                str(args.main_node_heavy_workers),
                "--worker-node-default-workers",
                str(args.worker_node_default_workers),
                "--worker-node-heavy-workers",
                str(args.worker_node_heavy_workers),
            ]

            if not args.cleanup_before_run:
                command.append("--no-cleanup-before-run")

        result = subprocess.run(command)

        if result.returncode != 0:
            raise SystemExit(result.returncode)

        run_dir = find_latest_run()
        analysis = load_analysis(run_dir)

        throughput = analysis.get("throughput", {})
        latency = analysis.get("latency", {})
        host = analysis.get("host", {})

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
                "max_queue_length": max_queue(run_dir),
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
    generate_sweep_report(sweep_dir)


if __name__ == "__main__":
    main()
