import csv
import json
import re
from pathlib import Path


ERROR_EVENTS = {
    "job_failed",
    "retry",
    "timeout",
    "rejected",
    "error",
}

TIMESTAMP_PATTERN = re.compile(r"^(\S+)\s+(.*)$")
K6_MSG_PATTERN = re.compile(r'msg="((?:\\.|[^"])*)"')


def generate_error_timeline(run_dir: Path) -> Path:
    rows = []

    log_files = list((run_dir / "logs").glob("*.log"))
    log_files += list((run_dir / "nodes").glob("*/logs/*.log"))

    for log_path in log_files:
        node = (
            log_path.parents[1].name
            if "nodes" in log_path.parts
            else "local"
        )
        container = log_path.stem

        for line in log_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            match = TIMESTAMP_PATTERN.match(line)

            if not match:
                continue

            timestamp, payload_text = match.groups()

            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                if "error" not in payload_text.lower():
                    continue

                rows.append(
                    {
                        "timestamp": timestamp,
                        "node": node,
                        "container": container,
                        "event": "unstructured_error",
                        "job_id": "",
                        "message": payload_text,
                    }
                )
                continue

            event = str(payload.get("event", ""))
            status = str(payload.get("status", ""))

            is_error = (
                event in ERROR_EVENTS
                or status == "FAILED"
                or payload.get("error") is not None
            )

            if not is_error:
                continue

            rows.append(
                {
                    "timestamp": timestamp,
                    "node": node,
                    "container": container,
                    "event": event or "error",
                    "job_id": payload.get("job_id", ""),
                    "message": payload.get(
                        "error",
                        payload.get("message", ""),
                    ),
                }
            )

    k6_stdout_path = run_dir / "k6_stdout.txt"

    if k6_stdout_path.exists():
        for line in k6_stdout_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines():
            match = K6_MSG_PATTERN.search(line)

            if not match:
                continue

            escaped_payload = match.group(1)

            try:
                payload_text = bytes(
                    escaped_payload,
                    "utf-8",
                ).decode("unicode_escape")

                payload = json.loads(payload_text)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue

            if payload.get("source") != "k6":
                continue

            rows.append(
                {
                    "timestamp": payload.get("timestamp", ""),
                    "node": "load-generator",
                    "container": "k6",
                    "event": payload.get("event", "k6_error"),
                    "job_id": payload.get("job_id", ""),
                    "message": payload.get(
                        "message",
                        payload.get("response_body", ""),
                    ),
                }
            )

    rows.sort(key=lambda row: row["timestamp"])

    output_path = run_dir / "error_timeline.csv"

    with output_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "timestamp",
                "node",
                "container",
                "event",
                "job_id",
                "message",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    return output_path
