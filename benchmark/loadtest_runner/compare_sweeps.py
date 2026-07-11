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
        label_nodes, path_text = entry.split("=", 1)
        label, node_count_text = label_nodes.rsplit(":", 1)
        node_count = int(node_count_text)
        rows = load_rows(Path(path_text))

        rates = [float(row["rate"]) for row in rows]
        throughputs = [
            float(row["completed_jobs_per_second"] or 0)
            for row in rows
        ]

        stable_rows = [row for row in rows if is_stable(row)]
        
        stable_throughput = (
            max(
                float(row["completed_jobs_per_second"] or 0)
                for row in stable_rows
            )
            if stable_rows
            else 0.0
        )

        max_stable_rate = (
            max(float(row["rate"]) for row in stable_rows)
            if stable_rows
            else None
        )

        peak_throughput = max(throughputs) if throughputs else 0

        summaries.append(
            {
                "setup": label,
                "node_count": node_count,
                "max_stable_rate": max_stable_rate,
                "stable_throughput": stable_throughput,
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
    
    plt.figure(figsize=(8, 5))

    nodes = [
		summary["node_count"]
		for summary in summaries
	]

    efficiencies = [
		summary["scaling_efficiency_percent"]
		for summary in summaries
	]

    plt.plot(
		nodes,
		efficiencies,
		marker="o",
	)

    plt.xlabel("Worker nodes")
    plt.ylabel("Scaling efficiency (%)")
    plt.title("Scaling efficiency")
    plt.grid(True)

    plt.tight_layout()
    plt.savefig(output_dir / "scaling_efficiency.png")
    plt.close()

    baseline = summaries[0]["stable_throughput"] if summaries else 0

    for summary in summaries:
        speedup = (
			summary["stable_throughput"] / baseline
			if baseline
			else None
		)

        summary["speedup_vs_baseline"] = speedup

        summary["scaling_efficiency_percent"] = (
			speedup / summary["node_count"] * 100
			if speedup is not None
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
				"node_count",
				"max_stable_rate",
				"stable_throughput",
				"peak_throughput",
				"speedup_vs_baseline",
				"scaling_efficiency_percent",
			],
        )
        writer.writeheader()
        writer.writerows(summaries)

    lines = [
		"# Sweep Comparison",
		"",
		"| Setup | Nodes | Max Stable Rate | Stable Throughput | Peak Throughput | Speedup | Efficiency |",
		"| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
	]

    for summary in summaries:
        speedup = summary["speedup_vs_baseline"]
        efficiency = summary["scaling_efficiency_percent"]

        lines.append(
			f"| {summary['setup']} "
			f"| {summary['node_count']} "
			f"| {summary['max_stable_rate'] if summary['max_stable_rate'] is not None else 'n/a'} "
			f"| {summary['stable_throughput']:.3f} "
			f"| {summary['peak_throughput']:.3f} "
			f"| {speedup:.2f}x "
			f"| {efficiency:.2f}% |"
		)

    lines.extend(
		[
			"",
			"## Plots",
			"",
			"- `throughput_comparison.png`",
			"- `scaling_efficiency.png`",
		]
	)

    (output_dir / "comparison_report.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print(f"Comparison written to: {output_dir}")


if __name__ == "__main__":
    main()