import csv
import argparse
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def parse_args():
    parser = argparse.ArgumentParser(description="Generate a sweep report.")
    parser.add_argument("sweep_dir")
    return parser.parse_args()


def is_stable(row: dict) -> bool:
    rate = float(row["rate"])
    throughput = float(row["completed_jobs_per_second"] or 0)
    failed = int(row["failed_jobs"] or 0)
    rejected = int(row["rejected_jobs"] or 0)
    errors = int(row["error_count"] or 0)
    max_queue = int(row.get("max_queue_length") or 0)

    return (
        throughput >= rate * 0.95
        and failed == 0
        and rejected == 0
        and errors == 0
        and max_queue == 0
    )


def run_report_link(sweep_dir: Path, row: dict) -> str:
    run_dir = row.get("run_dir")

    if not run_dir:
        return "n/a"

    report_path = Path(run_dir) / "report.md"
    link_target = os.path.relpath(
        report_path.resolve(),
        start=sweep_dir.resolve(),
    )

    return f"[report]({Path(link_target).as_posix()})"


def value(row: dict, key: str, fallback="n/a"):
    cell = row.get(key)

    if cell in (None, ""):
        return fallback

    return cell


def percent(row: dict, key: str) -> str:
    cell = row.get(key)

    if cell in (None, ""):
        return "n/a"

    return f"{cell}%"


def seconds(row: dict, key: str) -> str:
    cell = row.get(key)

    if cell in (None, ""):
        return "n/a"

    return f"{cell}s"


def float_values(rows: list[dict], key: str) -> list[float]:
    values = []

    for row in rows:
        cell = row.get(key)

        if cell in (None, ""):
            values.append(0.0)
        else:
            values.append(float(cell))

    return values


def generate_sweep_report(sweep_dir: Path) -> None:
    rows = load_rows(sweep_dir / "sweep_results.csv")

    rates = [float(row["rate"]) for row in rows]
    throughputs = [
        float(row["completed_jobs_per_second"] or 0)
        for row in rows
    ]
    latencies = [
        float(row["end_to_end_p95_ms"] or 0)
        for row in rows
    ]

    plt.figure(figsize=(8, 5))
    plt.plot(rates, throughputs, marker="o", label="Achieved throughput")
    plt.plot(rates, rates, linestyle="--", label="Ideal")
    plt.xlabel("Offered rate (jobs/s)")
    plt.ylabel("Completed jobs/s")
    plt.title("Offered load vs achieved throughput")
    plt.legend()
    plt.tight_layout()
    plt.savefig(sweep_dir / "throughput_vs_rate.png")
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(rates, latencies, marker="o")
    plt.xlabel("Offered rate (jobs/s)")
    plt.ylabel("End-to-end p95 latency (ms)")
    plt.title("Latency vs offered load")
    plt.tight_layout()
    plt.savefig(sweep_dir / "latency_vs_rate.png")
    plt.close()

    plot_files = [
        "throughput_vs_rate.png",
        "latency_vs_rate.png",
    ]

    if any(row.get("max_default_queue_length") for row in rows) or any(
        row.get("max_heavy_queue_length") for row in rows
    ):
        plt.figure(figsize=(8, 5))
        plt.plot(
            rates,
            float_values(rows, "max_default_queue_length"),
            marker="o",
            label="Default queue",
        )
        plt.plot(
            rates,
            float_values(rows, "max_heavy_queue_length"),
            marker="o",
            label="Heavy queue",
        )
        plt.xlabel("Offered rate (jobs/s)")
        plt.ylabel("Max queue length")
        plt.title("Queue pressure vs offered load")
        plt.legend()
        plt.tight_layout()
        plt.savefig(sweep_dir / "queue_vs_rate.png")
        plt.close()
        plot_files.append("queue_vs_rate.png")

    if any(row.get("avg_default_worker_cpu_percent") for row in rows) or any(
        row.get("avg_heavy_worker_cpu_percent") for row in rows
    ):
        plt.figure(figsize=(8, 5))
        plt.plot(
            rates,
            float_values(rows, "avg_default_worker_cpu_percent"),
            marker="o",
            label="Default workers",
        )
        plt.plot(
            rates,
            float_values(rows, "avg_heavy_worker_cpu_percent"),
            marker="o",
            label="Heavy workers",
        )
        plt.xlabel("Offered rate (jobs/s)")
        plt.ylabel("Average CPU (%)")
        plt.title("Worker CPU vs offered load")
        plt.legend()
        plt.tight_layout()
        plt.savefig(sweep_dir / "worker_cpu_vs_rate.png")
        plt.close()
        plot_files.append("worker_cpu_vs_rate.png")

    stable_rates = [
        float(row["rate"])
        for row in rows
        if is_stable(row)
    ]
    max_stable_rate = max(stable_rates) if stable_rates else None

    lines = [
        "# Sweep Report",
        "",
        f"- Maximum stable tested rate: `{max_stable_rate if max_stable_rate is not None else 'n/a'}` jobs/s",
        "",
        "## Results",
        "",
        "| Offered Rate | Throughput | p95 Latency | Host CPU | Default Q | Heavy Q | Default Drain | Heavy Drain | Default Worker CPU | Heavy Worker CPU | Errors | Stable | Run |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: | --- |",
    ]

    for row in rows:
        lines.append(
            f"| {row['rate']} "
            f"| {row['completed_jobs_per_second']} "
            f"| {row['end_to_end_p95_ms']} ms "
            f"| {percent(row, 'avg_cpu_percent')} "
            f"| {value(row, 'max_default_queue_length')} "
            f"| {value(row, 'max_heavy_queue_length')} "
            f"| {seconds(row, 'default_queue_drain_seconds')} "
            f"| {seconds(row, 'heavy_queue_drain_seconds')} "
            f"| {percent(row, 'avg_default_worker_cpu_percent')} "
            f"| {percent(row, 'avg_heavy_worker_cpu_percent')} "
            f"| {row['error_count']} "
            f"| {'yes' if is_stable(row) else 'no'} "
            f"| {run_report_link(sweep_dir, row)} |"
        )

    lines.extend(
        [
            "",
            "## Plots",
            "",
            *[
                f"- `{plot_file}`"
                for plot_file in plot_files
            ],
        ]
    )

    (sweep_dir / "sweep_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main():
    args = parse_args()
    generate_sweep_report(Path(args.sweep_dir))


if __name__ == "__main__":
    main()
