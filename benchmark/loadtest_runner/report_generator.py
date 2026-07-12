import argparse
import json
import csv
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Generate markdown benchmark report.")
    parser.add_argument("run_dir")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value, suffix=""):
    if value is None:
        return "n/a"
    return f"{value}{suffix}"

def count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0

    with path.open("r", encoding="utf-8") as file:
        return sum(1 for _ in csv.DictReader(file))


def should_report_container(name: str) -> bool:
    return (
        name.startswith("image-pipeline-")
        or name.startswith("docker-worker-")
    )


def display_container_name(name: str) -> str:
    for prefix in ("image-pipeline-", "docker-"):
        if name.startswith(prefix):
            return name.removeprefix(prefix)

    return name


def build_worker_summary_lines(run: dict) -> list[str]:
    main_default = run.get("main_node_default_workers")
    main_heavy = run.get("main_node_heavy_workers")
    worker_nodes = run.get("worker_nodes")
    worker_default = run.get("worker_node_default_workers")
    worker_heavy = run.get("worker_node_heavy_workers")
    default_workers = run.get("default_workers")
    heavy_workers = run.get("heavy_workers")
    total_workers = run.get("total_workers")

    if (
        main_default is None
        and main_heavy is None
        and worker_default is None
        and worker_heavy is None
    ):
        if default_workers is not None or heavy_workers is not None:
            if total_workers is None:
                total_workers = (default_workers or 0) + (heavy_workers or 0)

            return [
                f"- Default workers: `{default_workers or 0}`",
                f"- Heavy workers: `{heavy_workers or 0}`",
                f"- Total workers: `{total_workers}`",
            ]

        return [
            f"- Worker nodes: `{run.get('worker_nodes')}`",
            f"- Workers per node: `{run.get('workers_per_node')}`",
        ]

    if total_workers is None:
        total_workers = (default_workers or 0) + (heavy_workers or 0)

    if default_workers is None and main_default is not None:
        default_workers = main_default + (worker_nodes or 0) * (worker_default or 0)

    if heavy_workers is None and main_heavy is not None:
        heavy_workers = main_heavy + (worker_nodes or 0) * (worker_heavy or 0)

    return [
        f"- Main node default workers: `{main_default or 0}`",
        f"- Main node heavy workers: `{main_heavy or 0}`",
        f"- Worker nodes: `{worker_nodes or 0}`",
        f"- Worker node default workers each: `{worker_default or 0}`",
        f"- Worker node heavy workers each: `{worker_heavy or 0}`",
        f"- Total default workers: `{default_workers or 0}`",
        f"- Total heavy workers: `{heavy_workers or 0}`",
        f"- Total workers: `{total_workers}`",
    ]


def generate_report(run_dir: Path) -> Path:
    analysis = load_json(run_dir / "analysis_summary.json")
    error_count = count_csv_rows(run_dir / "error_timeline.csv")

    run = analysis["run"]
    throughput = analysis["throughput"]
    latency = analysis["latency"]
    workload = analysis["workload"]
    host = analysis["host"]
    docker = analysis["docker"]
    host_by_node = analysis.get("host_by_node", {})
    docker_by_node = analysis.get("docker_by_node", {})

    lines = [
        "# Benchmark Report",
        "",
        "## Run Configuration",
        "",
        f"- Profile: `{run.get('profile')}`",
        f"- Rate: `{run.get('rate')}` jobs/s",
        f"- Duration: `{run.get('duration')}`",
        f"- Environment: `{run.get('environment')}`",
        f"- Setup: `{run.get('setup')}`",
        *build_worker_summary_lines(run),
        "",
        "## Throughput",
        "",
        f"- Submitted jobs: `{throughput.get('submitted_jobs')}`",
        f"- Completed jobs: `{throughput.get('completed_jobs')}`",
        f"- Failed jobs: `{throughput.get('failed_jobs')}`",
        f"- Rejected jobs: `{throughput.get('rejected_jobs')}`",
        f"- Completed jobs/s: `{throughput.get('completed_jobs_per_second')}`",
        "",
        "## Latency",
        "",
        f"- End-to-end avg: `{fmt(latency.get('end_to_end_avg_ms'), ' ms')}`",
        f"- End-to-end p95: `{fmt(latency.get('end_to_end_p95_ms'), ' ms')}`",
        f"- HTTP avg: `{fmt(latency.get('http_req_avg_ms'), ' ms')}`",
        f"- HTTP p95: `{fmt(latency.get('http_req_p95_ms'), ' ms')}`",
        "",
        "## Host Utilization",
        "",
        f"- Avg CPU: `{fmt(host.get('avg_cpu_percent'), '%')}`",
        f"- Max CPU: `{fmt(host.get('max_cpu_percent'), '%')}`",
        f"- Avg memory: `{fmt(host.get('avg_memory_percent'), '%')}`",
        f"- Max memory: `{fmt(host.get('max_memory_percent'), '%')}`",
        f"- Avg load 1m: `{fmt(host.get('avg_load_1m'))}`",
        f"- Max load 1m: `{fmt(host.get('max_load_1m'))}`",
    ]

    lines.extend(
        [
            "",
            "## Timeline Observability",
            "",
            f"- Recorded errors/timeouts: `{error_count}`",
            "- Host CPU timeline: `timeline/host_cpu_timeline.png`",
            "- Queue timeline: `timeline/queue_timeline.png`",
            "- Error details: `error_timeline.csv`",
            "- Raw host metrics: `host_stats.csv`",
            "- Raw container metrics: `docker_stats.csv`",
            "- Raw queue metrics: `queue_stats.csv`",
        ]
    )

    if host_by_node:
        lines.extend(
            [
                "",
                "## Host Utilization by Node",
                "",
                "| Node | Avg CPU | Max CPU | Avg Memory | Max Memory | Avg Load 1m |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )

        for node_name, stats in host_by_node.items():
            lines.append(
                f"| {node_name} | "
                f"{fmt(stats.get('avg_cpu_percent'), '%')} | "
                f"{fmt(stats.get('max_cpu_percent'), '%')} | "
                f"{fmt(stats.get('avg_memory_percent'), '%')} | "
                f"{fmt(stats.get('max_memory_percent'), '%')} | "
                f"{fmt(stats.get('avg_load_1m'))} |"
            )

    host_io_by_node = analysis.get("host_io_by_node", {})

    lines.extend(
        [
            "",
            "## Host I/O by Node",
            "",
            "| Node | Disk Read | Disk Write | Network Sent | Network Received |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for node, values in host_io_by_node.items():
        lines.append(
            f"| {node} "
            f"| {values.get('disk_read_bytes_delta', 0) / 1024 / 1024:.2f} MB "
            f"| {values.get('disk_write_bytes_delta', 0) / 1024 / 1024:.2f} MB "
            f"| {values.get('network_bytes_sent_delta', 0) / 1024 / 1024:.2f} MB "
            f"| {values.get('network_bytes_recv_delta', 0) / 1024 / 1024:.2f} MB |"
        )

    lines.extend(
        [
            "",
            "## Workload Distribution",
            "",
            "| Task | Submitted | Completed | Share |",
            "| --- | ---: | ---: | ---: |",
        ]
    )

    for task in workload["task_distribution"].values():
        if task.get("submitted", 0) <= 0:
            continue

        lines.append(
            f"| {task.get('label')} | {task.get('submitted')} | "
            f"{task.get('completed')} | {task.get('submitted_percent')}% |"
        )

    lines.extend(
        [
            "",
            "## Container Utilization",
            "",
            "| Container | Avg CPU | Max CPU | Avg Memory | Max Memory |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for name, stats in docker.items():
        if not should_report_container(name):
            continue

        short_name = display_container_name(name)
        lines.append(
            f"| {short_name} | {fmt(stats.get('avg_cpu_percent'), '%')} | "
            f"{fmt(stats.get('max_cpu_percent'), '%')} | "
            f"{fmt(stats.get('avg_memory_percent'), '%')} | "
            f"{fmt(stats.get('max_memory_percent'), '%')} |"
        )

    if docker_by_node:
        lines.extend(
            [
                "",
                "## Container Utilization by Node",
                "",
            ]
        )

        for node_name, containers in docker_by_node.items():
            lines.extend(
                [
                    f"### {node_name}",
                    "",
                    "| Container | Avg CPU | Max CPU | Avg Memory | Max Memory |",
                    "| --- | ---: | ---: | ---: | ---: |",
                ]
            )

            for name, stats in containers.items():
                if not should_report_container(name):
                    continue

                short_name = display_container_name(name)

                lines.append(
                    f"| {short_name} | "
                    f"{fmt(stats.get('avg_cpu_percent'), '%')} | "
                    f"{fmt(stats.get('max_cpu_percent'), '%')} | "
                    f"{fmt(stats.get('avg_memory_percent'), '%')} | "
                    f"{fmt(stats.get('max_memory_percent'), '%')} |"
                )

            lines.append("")

    output_path = run_dir / "report.md"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def main():
    args = parse_args()
    output_path = generate_report(Path(args.run_dir))
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
