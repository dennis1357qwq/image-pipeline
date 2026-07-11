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
        f"- Worker nodes: `{run.get('worker_nodes')}`",
        f"- Workers per node: `{run.get('workers_per_node')}`",
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
        if not name.startswith("image-pipeline-"):
            continue

        short_name = name.replace("image-pipeline-", "")
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
                if not name.startswith("image-pipeline-"):
                    continue

                short_name = name.replace("image-pipeline-", "")

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
