import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


TIMESTAMP_PATTERN = re.compile(r"^(\S+)\s+(.*)$")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def generate_throughput_timeline(run_dir: Path) -> Path:
    completed_per_second: Counter[str] = Counter()

    log_files = list((run_dir / "logs").glob("*.log"))
    log_files += list((run_dir / "nodes").glob("*/logs/*.log"))

    for log_path in log_files:
        for line in log_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            match = TIMESTAMP_PATTERN.match(line)
            if not match:
                continue

            timestamp_text, payload_text = match.groups()

            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                continue

            if payload.get("event") != "job_finished":
                continue

            timestamp = parse_time(timestamp_text)
            second = timestamp.astimezone(timezone.utc).replace(
                microsecond=0
            ).isoformat()

            completed_per_second[second] += 1

    output_path = run_dir / "throughput_timeline.csv"

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["timestamp", "completed_jobs"],
        )
        writer.writeheader()

        for timestamp in sorted(completed_per_second):
            writer.writerow(
                {
                    "timestamp": timestamp,
                    "completed_jobs": completed_per_second[timestamp],
                }
            )

    return output_path