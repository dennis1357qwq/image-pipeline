import argparse
import csv
import json
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from datetime import datetime, timezone

from benchmark.loadtest_runner.analyze_results import analyze_run
from benchmark.loadtest_runner.node_config import (
    ClusterConfig,
    NodeConfig,
    load_cluster_config,
)
from benchmark.loadtest_runner.report_generator import generate_report
from benchmark.loadtest_runner.ssh_client import SSHClient
from benchmark.loadtest_runner.error_timeline import generate_error_timeline
from benchmark.loadtest_runner.timeline_report import generate_timeline_plots
from benchmark.loadtest_runner.throughput_timeline import (
    generate_throughput_timeline,
)


def should_collect_container_logs(container_name: str) -> bool:
    return (
        container_name.startswith("image-pipeline-")
        or container_name.startswith("docker-worker-")
    )


def cleanup_remote_node(client: SSHClient) -> None:
    client.run(
        "docker exec image-pipeline-redis redis-cli FLUSHDB",
        check=True,
    )

    client.run(
        "docker exec image-pipeline-postgres "
        "psql -U postgres -d image_pipeline "
        "-c 'TRUNCATE TABLE jobs;'",
        check=True,
    )

    client.run(
        "docker exec image-pipeline-minio "
        "mc alias set local http://localhost:9000 minioadmin minioadmin",
        check=True,
    )

    client.run(
        "docker exec image-pipeline-minio "
        "mc rm --recursive --force local/image-pipeline/",
        check=True,
    )

    client.run(
        "docker exec image-pipeline-minio "
        "mc mb --ignore-existing local/image-pipeline",
        check=True,
    )

def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a distributed benchmark and monitor all configured nodes."
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to the cluster JSON configuration.",
    )
    parser.add_argument("--profile", default="representative_mixed")
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--duration", default="30s")
    parser.add_argument("--poll-result", default="true")
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--poll-timeout-seconds", type=float, default=60.0)

    parser.add_argument(
        "--monitor-interval-seconds",
        type=float,
        default=1.0,
    )
    parser.add_argument(
        "--monitor-warmup-seconds",
        type=float,
        default=3.0,
        help="Baseline monitoring time before k6 starts.",
    )
    parser.add_argument(
        "--monitor-cooldown-seconds",
        type=float,
        default=3.0,
        help="Monitoring time after k6 finishes.",
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379/0",
    )
    parser.add_argument(
        "--main-node-default-workers",
        type=int,
        default=0,
        help="Number of default workers running on the main node.",
    )
    parser.add_argument(
        "--main-node-heavy-workers",
        type=int,
        default=0,
        help="Number of heavy workers running on the main node.",
    )
    parser.add_argument(
        "--worker-node-default-workers",
        type=int,
        default=0,
        help="Default workers running on each worker node.",
    )
    parser.add_argument(
        "--worker-node-heavy-workers",
        type=int,
        default=0,
        help="Heavy workers running on each worker node.",
    )

    parser.add_argument(
        "--remote-python",
        default="benchmark/venv/bin/python3",
        help="Python executable relative to the project directory on each VM.",
    )
    parser.add_argument(
        "--results-dir",
        default="results/loadtests",
    )
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--cleanup-before-run",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    return parser.parse_args()

def collect_remote_container_logs(
    cluster: ClusterConfig,
    clients: dict[str, SSHClient],
    run_dir: Path,
    since: datetime,
) -> None:
    since_value = since.astimezone(timezone.utc).isoformat()

    for node in cluster.nodes:
        client = clients[node.name]
        local_logs_dir = run_dir / "nodes" / node.name / "logs"
        local_logs_dir.mkdir(parents=True, exist_ok=True)

        result = client.run(
            "docker ps --format '{{.Names}}'",
            check=False,
        )

        if result.returncode != 0:
            continue

        containers = [
            name.strip()
            for name in result.stdout.splitlines()
            if should_collect_container_logs(name.strip())
        ]

        for container in containers:
            log_result = client.run(
                (
                    f"docker logs --timestamps "
                    f"--since {since_value} "
                    f"{container}"
                ),
                check=False,
            )

            (local_logs_dir / f"{container}.log").write_text(
                log_result.stdout + log_result.stderr,
                encoding="utf-8",
            )

def create_run_directory(args, cluster: ClusterConfig) -> tuple[Path, str]:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_id = uuid.uuid4().hex[:8]

    run_name = (
        f"{timestamp}_{cluster.name}_{args.profile}_"
        f"rate-{args.rate}_duration-{args.duration}_{run_id}"
    )

    run_dir = Path(args.results_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=False)

    return run_dir, run_id


def build_remote_run_dir(run_id: str) -> str:
    return f"/tmp/image-pipeline-benchmark/{run_id}"


def build_remote_monitor_command(
    node: NodeConfig,
    remote_run_dir: str,
    remote_python: str,
    interval_seconds: float,
    redis_url: str,
) -> str:
    return (
        f"cd {node.project_dir} && "
        f"{remote_python} -m benchmark.loadtest_runner.remote_monitor "
        f"--output-dir {remote_run_dir} "
        f"--node-name {node.name} "
        f"--interval-seconds {interval_seconds} "
        f"--redis-url {redis_url}"
    )


def check_api_health(api_url: str) -> None:
    health_url = f"{api_url.rstrip('/')}/health"

    result = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", health_url],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"API health check failed for {health_url}: "
            f"{result.stderr.strip()}"
        )

    print(f"API health check succeeded: {health_url}")


def check_ssh_connections(
    cluster: ClusterConfig,
) -> dict[str, SSHClient]:
    clients = {}

    for node in cluster.nodes:
        print(f"Checking SSH connection to {node.name} ({node.host})...")

        client = SSHClient(node)

        if not client.check_connection():
            raise RuntimeError(
                f"Could not establish non-interactive SSH connection "
                f"to node '{node.name}' at {node.host}"
            )

        clients[node.name] = client
        print(f"SSH connection successful: {node.name}")

    return clients


def start_remote_monitors(
    cluster: ClusterConfig,
    clients: dict[str, SSHClient],
    remote_run_dir: str,
    args,
) -> dict[str, int]:
    pids = {}

    for node in cluster.nodes:
        client = clients[node.name]
        client.create_directory(remote_run_dir)

        command = build_remote_monitor_command(
            node=node,
            remote_run_dir=remote_run_dir,
            remote_python=args.remote_python,
            interval_seconds=args.monitor_interval_seconds,
            redis_url=args.redis_url,
        )

        pid = client.start_background(
            remote_command=command,
            stdout_path=f"{remote_run_dir}/monitor_stdout.log",
            stderr_path=f"{remote_run_dir}/monitor_stderr.log",
        )

        pids[node.name] = pid
        print(f"Started monitor on {node.name}, PID={pid}")

    return pids


def stop_remote_monitors(
    cluster: ClusterConfig,
    clients: dict[str, SSHClient],
    pids: dict[str, int],
) -> None:
    for node in cluster.nodes:
        pid = pids.get(node.name)

        if pid is None:
            continue

        try:
            clients[node.name].stop_process(pid)
            print(f"Stopped monitor on {node.name}, PID={pid}")
        except Exception as error:
            print(
                f"Warning: could not stop monitor on "
                f"{node.name}: {error}"
            )


def run_k6(
    args,
    cluster: ClusterConfig,
    run_dir: Path,
) -> subprocess.CompletedProcess:
    workload_summary_path = run_dir / "workload_summary.json"
    k6_summary_path = run_dir / "k6_summary.json"

    env = os.environ.copy()
    env.update(
        {
            "BASE_URL": cluster.api_url,
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

    print("Running:", " ".join(command))

    return subprocess.run(
        command,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def download_node_results(
    cluster: ClusterConfig,
    clients: dict[str, SSHClient],
    remote_run_dir: str,
    run_dir: Path,
) -> None:
    nodes_dir = run_dir / "nodes"

    for node in cluster.nodes:
        local_node_dir = nodes_dir / node.name
        local_node_dir.mkdir(parents=True, exist_ok=True)

        client = clients[node.name]

        filenames = [
            "host_stats.csv",
            "docker_stats.csv",
            "queue_stats.csv",
            "monitor_stdout.log",
            "monitor_stderr.log",
        ]

        for filename in filenames:
            remote_path = f"{remote_run_dir}/{filename}"
            local_path = local_node_dir / filename

            try:
                client.download_file(remote_path, local_path)
                print(f"Downloaded {node.name}/{filename}")
            except subprocess.CalledProcessError:
                if filename.endswith(".csv"):
                    raise

                print(
                    f"Warning: could not download "
                    f"{node.name}/{filename}"
                )


def merge_csv_files(
    input_paths: list[Path],
    output_path: Path,
) -> None:
    existing_paths = [path for path in input_paths if path.exists()]

    if not existing_paths:
        raise RuntimeError(
            f"No input CSV files found for {output_path.name}"
        )

    fieldnames = None

    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = None

        for input_path in existing_paths:
            with input_path.open(
                "r",
                newline="",
                encoding="utf-8",
            ) as input_file:
                reader = csv.DictReader(input_file)

                if reader.fieldnames is None:
                    continue

                if fieldnames is None:
                    fieldnames = reader.fieldnames
                    writer = csv.DictWriter(
                        output_file,
                        fieldnames=fieldnames,
                    )
                    writer.writeheader()
                elif reader.fieldnames != fieldnames:
                    raise ValueError(
                        f"CSV schema mismatch in {input_path}"
                    )

                for row in reader:
                    writer.writerow(row)


def merge_node_results(
    cluster: ClusterConfig,
    run_dir: Path,
) -> None:
    host_paths = [
        run_dir / "nodes" / node.name / "host_stats.csv"
        for node in cluster.nodes
    ]

    docker_paths = [
        run_dir / "nodes" / node.name / "docker_stats.csv"
        for node in cluster.nodes
    ]

    queue_paths = [
        run_dir / "nodes" / node.name / "queue_stats.csv"
        for node in cluster.nodes
    ]

    merge_csv_files(
        input_paths=host_paths,
        output_path=run_dir / "host_stats.csv",
    )

    merge_csv_files(
        input_paths=docker_paths,
        output_path=run_dir / "docker_stats.csv",
    )

    merge_csv_files(
        input_paths=queue_paths,
        output_path=run_dir / "queue_stats.csv",
    )


def write_config(
    args,
    cluster: ClusterConfig,
    run_dir: Path,
) -> Path:
    worker_nodes = [
        node for node in cluster.nodes if node.role == "worker"
    ]

    main_node = next(
        node for node in cluster.nodes if node.role == "main"
    )
    total_default_workers = (
        args.main_node_default_workers
        + len(worker_nodes) * args.worker_node_default_workers
    )
    total_heavy_workers = (
        args.main_node_heavy_workers
        + len(worker_nodes) * args.worker_node_heavy_workers
    )

    config = {
        "timestamp": datetime.now().isoformat(),
        "base_url": cluster.api_url,
        "profile": args.profile,
        "rate": args.rate,
        "duration": args.duration,
        "poll_result": args.poll_result,
        "poll_interval_seconds": args.poll_interval_seconds,
        "poll_timeout_seconds": args.poll_timeout_seconds,
        "environment": "gcp",
        "setup": cluster.name,
        "total_nodes": len(cluster.nodes),
        "worker_nodes": len(worker_nodes),
        "workers_per_node": None,
        "main_node_default_workers": args.main_node_default_workers,
        "main_node_heavy_workers": args.main_node_heavy_workers,
        "worker_node_default_workers": args.worker_node_default_workers,
        "worker_node_heavy_workers": args.worker_node_heavy_workers,
        "default_workers": total_default_workers,
        "heavy_workers": total_heavy_workers,
        "total_workers": total_default_workers + total_heavy_workers,
        "main_node": main_node.name,
        "monitor_interval_seconds": args.monitor_interval_seconds,
        "monitor_warmup_seconds": args.monitor_warmup_seconds,
        "monitor_cooldown_seconds": args.monitor_cooldown_seconds,
        "nodes": [
            {
                "name": node.name,
                "role": node.role,
                "host": node.host,
            }
            for node in cluster.nodes
        ],
        "notes": args.notes,
    }

    path = run_dir / "config.json"
    path.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    return path


def update_config_file(path: Path, updates: dict) -> None:
    config = json.loads(path.read_text(encoding="utf-8"))
    config.update(updates)
    path.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )


def update_latest(results_dir: str, run_dir: Path) -> Path:
    latest_path = Path(results_dir) / "latest"

    if latest_path.exists() or latest_path.is_symlink():
        if latest_path.is_symlink() or latest_path.is_file():
            latest_path.unlink()
        else:
            shutil.rmtree(latest_path)

    try:
        latest_path.symlink_to(
            run_dir.resolve(),
            target_is_directory=True,
        )
    except OSError:
        shutil.copytree(run_dir, latest_path)

    return latest_path


def main():
    args = parse_args()

    cluster = load_cluster_config(Path(args.config))
    run_dir, run_id = create_run_directory(args, cluster)
    remote_run_dir = build_remote_run_dir(run_id)

    print(f"Cluster: {cluster.name}")
    print(f"API URL: {cluster.api_url}")
    print(f"Nodes: {len(cluster.nodes)}")
    print(f"Run directory: {run_dir}")

    config_path = write_config(args, cluster, run_dir)

    check_api_health(cluster.api_url)
    clients = check_ssh_connections(cluster)

    main_node = next(
        node for node in cluster.nodes
        if node.role == "main"
    )

    main_client = clients[main_node.name]

    if args.cleanup_before_run:
        print("Cleaning cluster...")
        cleanup_remote_node(main_client)

    monitor_pids = {}
    k6_result = None
    run_started_at = datetime.now(timezone.utc)
    update_config_file(
        config_path,
        {"run_started_at": run_started_at.isoformat()},
    )

    try:
        monitor_pids = start_remote_monitors(
            cluster=cluster,
            clients=clients,
            remote_run_dir=remote_run_dir,
            args=args,
        )

        print(
            f"Collecting baseline metrics for "
            f"{args.monitor_warmup_seconds} seconds..."
        )
        time.sleep(args.monitor_warmup_seconds)

        k6_result = run_k6(
            args=args,
            cluster=cluster,
            run_dir=run_dir,
        )

        (run_dir / "k6_stdout.txt").write_text(
            k6_result.stdout,
            encoding="utf-8",
        )

        print(
            f"Collecting cooldown metrics for "
            f"{args.monitor_cooldown_seconds} seconds..."
        )
        time.sleep(args.monitor_cooldown_seconds)

    finally:
        stop_remote_monitors(
            cluster=cluster,
            clients=clients,
            pids=monitor_pids,
        )

        time.sleep(2)

        if monitor_pids:
            download_node_results(
                cluster=cluster,
                clients=clients,
                remote_run_dir=remote_run_dir,
                run_dir=run_dir,
            )
            collect_remote_container_logs(
                cluster=cluster,
                clients=clients,
                run_dir=run_dir,
                since=run_started_at,
            )

    if k6_result is None:
        raise RuntimeError("k6 was not started")

    if k6_result.returncode != 0:
        print(k6_result.stdout)
        raise SystemExit(k6_result.returncode)

    merge_node_results(
        cluster=cluster,
        run_dir=run_dir,
    )

    generate_error_timeline(run_dir)
    generate_throughput_timeline(run_dir)
    generate_timeline_plots(run_dir)

    analysis_path = analyze_run(run_dir)
    report_path = generate_report(run_dir)
    latest_path = update_latest(args.results_dir, run_dir)

    print()
    print("Distributed benchmark finished successfully.")
    print(f"Config: {config_path}")
    print(f"Analysis: {analysis_path}")
    print(f"Report: {report_path}")
    print(f"Latest run: {latest_path}")


if __name__ == "__main__":
    main()
