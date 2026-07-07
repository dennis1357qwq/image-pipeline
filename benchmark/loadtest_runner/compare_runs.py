import argparse
import json
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Compare benchmark runs.")
    parser.add_argument("run_dirs", nargs="+")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value):
    if value is None:
        return "n/a"
    return str(value)


def main():
    args = parse_args()

    rows = []

    for run_dir_raw in args.run_dirs:
        run_dir = Path(run_dir_raw)
        analysis = load_json(run_dir / "analysis_summary.json")

        run = analysis["run"]
        throughput = analysis["throughput"]
        latency = analysis["latency"]
        host = analysis["host"]

        rows.append(
            {
                "run": run_dir.name,
                "profile": run.get("profile"),
                "rate": run.get("rate"),
                "duration": run.get("duration"),
                "setup": run.get("setup"),
                "workers": run.get("workers_per_node"),
                "completed": throughput.get("completed_jobs"),
                "throughput": throughput.get("completed_jobs_per_second"),
                "p95_ms": latency.get("end_to_end_p95_ms"),
                "avg_cpu": host.get("avg_cpu_percent"),
                "max_cpu": host.get("max_cpu_percent"),
            }
        )

    print("| Run | Profile | Rate | Duration | Setup | Workers/Node | Completed | Throughput | P95 E2E ms | Avg CPU | Max CPU |")
    print("| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")

    for row in rows:
        print(
            f"| {row['run']} | {row['profile']} | {row['rate']} | {row['duration']} | "
            f"{row['setup']} | {row['workers']} | {row['completed']} | "
            f"{fmt(row['throughput'])} | {fmt(row['p95_ms'])} | "
            f"{fmt(row['avg_cpu'])} | {fmt(row['max_cpu'])} |"
        )


if __name__ == "__main__":
    main()