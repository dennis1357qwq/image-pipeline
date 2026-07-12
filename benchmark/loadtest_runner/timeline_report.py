import argparse
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt

from benchmark.loadtest_runner.analyze_results import parse_duration_seconds


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def parse_args():
    parser = argparse.ArgumentParser(description="Generate timeline plots.")
    parser.add_argument("run_dir")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}

    return json.loads(path.read_text(encoding="utf-8"))


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_load_end_time(config: dict) -> datetime | None:
    run_started_at = config.get("run_started_at")
    duration = config.get("duration")

    if not run_started_at or not duration:
        return None

    return parse_time(run_started_at) + timedelta(
        seconds=parse_duration_seconds(duration)
    )


def draw_load_end_marker(ax, load_end_time: datetime | None) -> None:
    if load_end_time is None:
        return

    ax.axvline(
        load_end_time,
        color="black",
        linestyle="--",
        linewidth=1.2,
        alpha=0.75,
        label="End of load injection",
    )
    ax.annotate(
        "End of load injection",
        xy=(load_end_time, 0.98),
        xycoords=("data", "axes fraction"),
        rotation=90,
        va="top",
        ha="right",
        fontsize=8,
        color="black",
    )


def draw_error_markers(ax, error_times: list[datetime]) -> None:
    for index, timestamp in enumerate(error_times):
        ax.axvline(
            timestamp,
            color="tab:red",
            linestyle=":",
            linewidth=1.0,
            alpha=0.45,
            label="Error/timeout" if index == 0 else None,
        )


def generate_timeline_plots(run_dir: Path) -> list[Path]:
    output_dir = run_dir / "timeline"
    output_dir.mkdir(parents=True, exist_ok=True)

    outputs = []

    host_rows = load_csv(run_dir / "host_stats.csv")
    queue_rows = load_csv(run_dir / "queue_stats.csv")
    error_rows = load_csv(run_dir / "error_timeline.csv")
    throughput_rows = load_csv(run_dir / "throughput_timeline.csv")
    config = load_json(run_dir / "config.json")
    load_end_time = get_load_end_time(config)

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

        _, ax = plt.subplots(figsize=(10, 5))

        for node, rows in by_node.items():
            ax.plot(
                [parse_time(row["timestamp"]) for row in rows],
                [float(row["cpu_percent"]) for row in rows],
                label=node,
            )

        draw_error_markers(ax, error_times)

        draw_load_end_marker(ax, load_end_time)

        ax.set_xlabel("Time")
        ax.set_ylabel("CPU (%)")
        ax.set_title("Host CPU utilization over time")
        ax.legend()
        plt.tight_layout()

        path = output_dir / "host_cpu_timeline.png"
        plt.savefig(path)
        plt.close()
        outputs.append(path)

    # Queue lengths
    if queue_rows:
        _, ax = plt.subplots(figsize=(10, 5))

        ax.plot(
            [parse_time(row["timestamp"]) for row in queue_rows],
            [int(row["default_queue_length"] or 0) for row in queue_rows],
            label="Default queue",
        )
        ax.plot(
            [parse_time(row["timestamp"]) for row in queue_rows],
            [int(row["heavy_queue_length"] or 0) for row in queue_rows],
            label="Heavy queue",
        )

        draw_error_markers(ax, error_times)

        draw_load_end_marker(ax, load_end_time)

        ax.set_xlabel("Time")
        ax.set_ylabel("Queued jobs")
        ax.set_title("Queue length over time")
        ax.legend()
        plt.tight_layout()

        path = output_dir / "queue_timeline.png"
        plt.savefig(path)
        plt.close()
        outputs.append(path)
        
    if throughput_rows:
        _, ax = plt.subplots(figsize=(10, 5))

        ax.plot(
            [parse_time(row["timestamp"]) for row in throughput_rows],
            [int(row["completed_jobs"]) for row in throughput_rows],
            marker="o",
            label="Completed jobs/s",
        )

        draw_error_markers(ax, error_times)

        draw_load_end_marker(ax, load_end_time)

        ax.set_xlabel("Time")
        ax.set_ylabel("Completed jobs/s")
        ax.set_title("Throughput over time")
        ax.legend()
        plt.tight_layout()

        path = output_dir / "throughput_timeline.png"
        plt.savefig(path)
        plt.close()
        outputs.append(path)

    return outputs


def main():
    args = parse_args()
    generate_timeline_plots(Path(args.run_dir))


if __name__ == "__main__":
    main()
