import csv
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def generate_timeline_plots(run_dir: Path) -> list[Path]:
    output_dir = run_dir / "timeline"
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = []

    host_rows = load_csv(run_dir / "host_stats.csv")
    queue_rows = load_csv(run_dir / "queue_stats.csv")
    error_rows = load_csv(run_dir / "error_timeline.csv")

    error_times = [
        parse_time(row["timestamp"])
        for row in error_rows
        if row.get("timestamp")
    ]

    # Host CPU
    if host_rows:
        by_node: dict[str, list[dict]] = {}

        for row in host_rows:
            by_node.setdefault(row["node"], []).append(row)

        plt.figure(figsize=(10, 5))

        for node, rows in by_node.items():
            plt.plot(
                [parse_time(row["timestamp"]) for row in rows],
                [float(row["cpu_percent"]) for row in rows],
                label=node,
            )

        for timestamp in error_times:
            plt.axvline(timestamp, linestyle="--", alpha=0.4)

        plt.xlabel("Time")
        plt.ylabel("CPU (%)")
        plt.title("Host CPU utilization over time")
        plt.legend()
        plt.tight_layout()

        path = output_dir / "host_cpu_timeline.png"
        plt.savefig(path)
        plt.close()
        outputs.append(path)

    # Queue lengths
    if queue_rows:
        plt.figure(figsize=(10, 5))

        plt.plot(
            [parse_time(row["timestamp"]) for row in queue_rows],
            [int(row["default_queue_length"] or 0) for row in queue_rows],
            label="Default queue",
        )
        plt.plot(
            [parse_time(row["timestamp"]) for row in queue_rows],
            [int(row["heavy_queue_length"] or 0) for row in queue_rows],
            label="Heavy queue",
        )

        for timestamp in error_times:
            plt.axvline(timestamp, linestyle="--", alpha=0.4)

        plt.xlabel("Time")
        plt.ylabel("Queued jobs")
        plt.title("Queue length over time")
        plt.legend()
        plt.tight_layout()

        path = output_dir / "queue_timeline.png"
        plt.savefig(path)
        plt.close()
        outputs.append(path)

    return outputs