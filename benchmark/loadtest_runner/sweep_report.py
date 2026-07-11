import csv
from pathlib import Path

import matplotlib.pyplot as plt


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def is_stable(row: dict) -> bool:
    rate = float(row["rate"])
    throughput = float(row["completed_jobs_per_second"] or 0)
    failed = int(row["failed_jobs"] or 0)
    rejected = int(row["rejected_jobs"] or 0)
    errors = int(row["error_count"] or 0)
    max_queue = int(row["max_queue_length"] or 0)

    return (
        throughput >= rate * 0.95
        and failed == 0
        and rejected == 0
        and errors == 0
        and max_queue == 0
    )


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
        "| Offered Rate | Throughput | p95 Latency | Avg CPU | Max Queue | Errors | Stable |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]

    for row in rows:
        lines.append(
            f"| {row['rate']} "
            f"| {row['completed_jobs_per_second']} "
            f"| {row['end_to_end_p95_ms']} ms "
            f"| {row['avg_cpu_percent']}% "
            f"| {row['max_queue_length']} "
            f"| {row['error_count']} "
            f"| {'yes' if is_stable(row) else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Plots",
            "",
            "- `throughput_vs_rate.png`",
            "- `latency_vs_rate.png`",
        ]
    )

    (sweep_dir / "sweep_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )