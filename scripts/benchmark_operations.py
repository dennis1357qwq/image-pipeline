import argparse
import csv
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, __version__ as pillow_version

from benchmark.benchmark_cases import BENCHMARK_CASES
from worker.app.image_processor import process_image


def get_git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def pipeline_to_json_like(pipeline) -> str:
    return str(
        [
            {
                "operation": step.operation,
                "parameters": step.parameters,
            }
            for step in pipeline
        ]
    )


def benchmark_case(image: Image.Image, pipeline, iterations: int, warmup: int) -> dict:
    for _ in range(warmup):
        process_image(image.copy(), pipeline)

    wall_times = []
    cpu_times = []

    for _ in range(iterations):
        image_copy = image.copy()

        wall_start = time.perf_counter()
        cpu_start = time.process_time()

        process_image(image_copy, pipeline)

        cpu_times.append(time.process_time() - cpu_start)
        wall_times.append(time.perf_counter() - wall_start)

    return {
        "mean_wall_ms": statistics.mean(wall_times) * 1000,
        "median_wall_ms": statistics.median(wall_times) * 1000,
        "min_wall_ms": min(wall_times) * 1000,
        "max_wall_ms": max(wall_times) * 1000,
        "stdev_wall_ms": statistics.stdev(wall_times) * 1000 if len(wall_times) > 1 else 0,
        "mean_cpu_ms": statistics.mean(cpu_times) * 1000,
        "median_cpu_ms": statistics.median(cpu_times) * 1000,
        "min_cpu_ms": min(cpu_times) * 1000,
        "max_cpu_ms": max(cpu_times) * 1000,
        "stdev_cpu_ms": statistics.stdev(cpu_times) * 1000 if len(cpu_times) > 1 else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--output", required=True)
    parser.add_argument("--shuffle", action="store_true")
    args = parser.parse_args()

    image_path = Path(args.image)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as image:
        input_image = image.convert("RGB")

    cases = list(BENCHMARK_CASES.items())

    if args.shuffle:
        random.shuffle(cases)

    rows = []

    for case_name, pipeline in cases:
        print(f"Benchmarking {case_name}...")
        measurements = benchmark_case(
            image=input_image,
            pipeline=pipeline,
            iterations=args.iterations,
            warmup=args.warmup,
        )

        rows.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "git_commit": get_git_commit(),
                "environment": os.getenv("BENCHMARK_ENVIRONMENT", "local"),
                "machine": platform.node(),
                "platform": platform.platform(),
                "processor": platform.processor(),
                "python_version": sys.version.replace("\n", " "),
                "pillow_version": pillow_version,
                "cpu_count": os.cpu_count(),
                "image_path": str(image_path),
                "image_width": input_image.width,
                "image_height": input_image.height,
                "image_format": image_path.suffix.lower().replace(".", ""),
                "iterations": args.iterations,
                "warmup": args.warmup,
                "case_name": case_name,
                "pipeline": pipeline_to_json_like(pipeline),
                **measurements,
            }
        )

    fieldnames = list(rows[0].keys())

    with output_path.open("w", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote benchmark results to {output_path}")


if __name__ == "__main__":
    main()