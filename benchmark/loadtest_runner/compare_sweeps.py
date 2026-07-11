import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare multiple benchmark sweeps."
    )
    parser.add_argument(
        "--sweeps",
        nargs="+",
        required=True,
        help="Entries formatted as label=path/to/sweep_results.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="results/comparisons/latest",
    )
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def is_stable(row: dict) -> bool:
    rate = float(row["rate"])
    throughput = float(row["completed_jobs_per_second"] or 0)

    return (
        throughput >= rate * 0.90
        and int(row["failed_jobs"] or 0) == 0
        and int(row["rejected_jobs"] or 0) == 0
        and int(row["error_count"] or 0) == 0
        and int(row["max_queue_length"] or 0) == 0
    )


def main():
    args = parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries = []

    plt.figure(figsize=(9, 6))

    for entry in args.sweeps:
        label, path_text = entry.split("=", 1)
        rows = load_rows(Path(path_text))

        rates = [float(row["rate"]) for row in rows]
        throughputs = [
            float(row["completed_jobs_per_second"] or 0)
            for row in rows
        ]

        stable_rows = [row for row in rows if is_stable(row)]

        max_stable_rate = (
            max(float(row["rate"]) for row in stable_rows)
            if stable_rows
            else None
        )

        peak_throughput = max(throughputs) if throughputs else 0

        summaries.append(
            {
                "setup": label,
                "max_stable_rate": max_stable_rate,
                "peak_throughput": peak_throughput,
            }
        )

        plt.plot(
            rates,
            throughputs,
            marker="o",
            label=label,
        )

    plt.xlabel("Offered rate (jobs/s)")
    plt.ylabel("Completed jobs/s")
    plt.title("Sweep comparison")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_dir / "throughput_comparison.png")
    plt.close()

    baseline = summaries[0]["peak_throughput"] if summaries else 0

    for summary in summaries:
        summary["speedup_vs_baseline"] = (
            summary["peak_throughput"] / baseline
            if baseline
            else None
        )

    csv_path = output_dir / "comparison_results.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "setup",
                "max_stable_rate",
                "peak_throughput",
                "speedup_vs_baseline",
            ],
        )
        writer.writeheader()
        writer.writerows(summaries)

    lines = [
        "# Sweep Comparison",
        "",
        "| Setup | Max Stable Rate | Peak Throughput | Speedup vs Baseline |",
        "| --- | ---: | ---: | ---: |",
    ]

    for summary in summaries:
        speedup = summary["speedup_vs_baseline"]

        lines.append(
            f"| {summary['setup']} "
            f"| {summary['max_stable_rate'] if summary['max_stable_rate'] is not None else 'n/a'} "
            f"| {summary['peak_throughput']:.3f} "
            f"| {speedup:.2f}x |"
        )

    lines.extend(
        [
            "",
            "## Plot",
            "",
            "- `throughput_comparison.png`",
        ]
    )

    (output_dir / "comparison_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"Comparison written to: {output_dir}")


if __name__ == "__main__":
    main()