import argparse
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from datetime import datetime, timezone
import shutil
from benchmark.loadtest_runner.analyze_results import analyze_run
from benchmark.loadtest_runner.docker_monitor import DockerMonitor
from benchmark.loadtest_runner.report_generator import generate_report
from benchmark.loadtest_runner.queue_monitor import QueueMonitor
from benchmark.loadtest_runner.error_timeline import generate_error_timeline
from benchmark.loadtest_runner.timeline_report import generate_timeline_plots
from benchmark.loadtest_runner.throughput_timeline import (generate_throughput_timeline)
from benchmark.loadtest_runner.cleanup import cleanup_local_environment

def parse_args():
    parser = argparse.ArgumentParser(description="Run k6 benchmark and store results.")

    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--profile", default="representative_mixed")
    parser.add_argument("--rate", type=float, default=1)
    parser.add_argument("--duration", default="30s")
    parser.add_argument("--poll-result", default="true")
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--poll-timeout-seconds", type=float, default=60.0)

    parser.add_argument("--environment", default="local")
    parser.add_argument("--setup", default="unknown")
    parser.add_argument("--worker-nodes", type=int, default=1)
    parser.add_argument("--workers-per-node", type=int, default=1)

    parser.add_argument("--results-dir", default="results/loadtests")
    parser.add_argument("--notes", default="")

    parser.add_argument("--monitor-docker", action="store_true")
    parser.add_argument("--monitor-node-name", default="local")
    parser.add_argument("--monitor-interval-seconds", type=float, default=1.0)
    parser.add_argument("--monitor-queue",action="store_true",)
    parser.add_argument("--redis-url",default="redis://localhost:6379/0",)
    parser.add_argument("--cleanup-before-run", action="store_true")

    return parser.parse_args()

def collect_container_logs(
    run_dir: Path,
    since: datetime,
    containers: list[str],
) -> None:
    since_value = since.astimezone(timezone.utc).isoformat()

    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    for container in containers:
        result = subprocess.run(
            [
                "docker",
                "logs",
                "--timestamps",
                "--since",
                since_value,
                container,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        (logs_dir / f"{container}.log").write_text(
            result.stdout,
            encoding="utf-8",
        )

def main():
    args = parse_args()

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_name = f"{timestamp}_{args.profile}_rate-{args.rate}_duration-{args.duration}"
    run_dir = Path(args.results_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "timestamp": timestamp,
        "base_url": args.base_url,
        "profile": args.profile,
        "rate": args.rate,
        "duration": args.duration,
        "poll_result": args.poll_result,
        "poll_interval_seconds": args.poll_interval_seconds,
        "poll_timeout_seconds": args.poll_timeout_seconds,
        "environment": args.environment,
        "setup": args.setup,
        "worker_nodes": args.worker_nodes,
        "workers_per_node": args.workers_per_node,
        "monitor_docker": args.monitor_docker,
        "monitor_node_name": args.monitor_node_name,
        "monitor_interval_seconds": args.monitor_interval_seconds,
        "notes": args.notes,
    }

    config_path = run_dir / "config.json"
    workload_summary_path = run_dir / "workload_summary.json"
    k6_summary_path = run_dir / "k6_summary.json"
    stdout_path = run_dir / "k6_stdout.txt"
    docker_stats_path = run_dir / "docker_stats.csv"
    host_stats_path = run_dir / "host_stats.csv"
    queue_stats_path = run_dir / "queue_stats.csv"

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "BASE_URL": args.base_url,
            "PROFILE": args.profile,
            "RATE": str(args.rate),
            "DURATION": args.duration,
            "POLL_RESULT": args.poll_result,
            "POLL_INTERVAL_SECONDS": str(args.poll_interval_seconds),
            "POLL_TIMEOUT_SECONDS": str(args.poll_timeout_seconds),
            "WORKLOAD_SUMMARY_PATH": str(workload_summary_path),
        }
    )

    command = [
        "k6",
        "run",
        "--summary-export",
        str(k6_summary_path),
        "loadtests/jobs.js",
    ]

    print(f"Run directory: {run_dir}")
    print("Running:", " ".join(command))

    monitor = None
    queue_monitor = None
    if args.cleanup_before_run:
        print("Cleaning environment before benchmark...")
        cleanup_local_environment()
    run_started_at = datetime.now(timezone.utc)

    config["run_started_at"] = run_started_at.isoformat()
    config_path.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    if args.monitor_docker:
        monitor = DockerMonitor(
            docker_output_path=docker_stats_path,
            host_output_path=host_stats_path,
            node_name=args.monitor_node_name,
            interval_seconds=args.monitor_interval_seconds,
        )
        monitor.start()

    if args.monitor_queue:
        queue_monitor = QueueMonitor(
            output_path=queue_stats_path,
            node_name=args.monitor_node_name,
            redis_url=args.redis_url,
            interval_seconds=args.monitor_interval_seconds,
        )
        queue_monitor.start()

    try:
        result = subprocess.run(
            command,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    finally:
        if queue_monitor is not None:
            queue_monitor.stop()
            
        if monitor is not None:
            monitor.stop()

    stdout_path.write_text(result.stdout, encoding="utf-8")

    collect_container_logs(
        run_dir=run_dir,
        since=run_started_at,
        containers=[
            "image-pipeline-api",
            "image-pipeline-worker-default",
            "image-pipeline-worker-heavy",
            "image-pipeline-redis",
            "image-pipeline-postgres",
            "image-pipeline-minio",
        ],
    )

    generate_error_timeline(run_dir)
    generate_throughput_timeline(run_dir)
    generate_timeline_plots(run_dir)

    analysis_path = None
    report_path = None

    if result.returncode == 0:
        analysis_path = analyze_run(run_dir)
        report_path = generate_report(run_dir)

    latest_path = Path(args.results_dir) / "latest"

    if latest_path.exists() or latest_path.is_symlink():
        if latest_path.is_dir() and not latest_path.is_symlink():
            shutil.rmtree(latest_path)
        else:
            latest_path.unlink()

    try:
        latest_path.symlink_to(run_dir.resolve(), target_is_directory=True)
    except OSError:
        shutil.copytree(run_dir, latest_path)

    if result.returncode != 0:
        print(result.stdout)
        raise SystemExit(result.returncode)

    if analysis_path is not None:
        print(f"Analysis summary: {analysis_path}")

    if report_path is not None:
        print(f"Report: {report_path}")

    print(f"Report: {report_path}")
    print(f"Latest run: {latest_path}")
    print("Benchmark finished successfully.")
    print(f"Config: {config_path}")
    print(f"k6 summary: {k6_summary_path}")
    print(f"Workload summary: {workload_summary_path}")
    print(f"stdout: {stdout_path}")

    if args.monitor_docker:
        print(f"Docker stats: {docker_stats_path}")
        print(f"Host stats: {host_stats_path}")

    if args.monitor_queue:
        print(f"Queue stats: {queue_stats_path}")


if __name__ == "__main__":
    main()
