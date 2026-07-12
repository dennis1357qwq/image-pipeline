import csv
import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


def list_compose_service_containers(service: str) -> list[str]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.service={service}",
            "--format",
            "{{.Names}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return [
        name.strip()
        for name in result.stdout.splitlines()
        if name.strip()
    ]


class DockerMonitor:
    def __init__(
        self,
        docker_output_path: Path,
        host_output_path: Path,
        node_name: str = "local",
        interval_seconds: float = 1.0,
    ):
        self.docker_output_path = Path(docker_output_path)
        self.host_output_path = Path(host_output_path)
        self.node_name = node_name
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        self.docker_output_path.parent.mkdir(parents=True, exist_ok=True)
        self.host_output_path.parent.mkdir(parents=True, exist_ok=True)

        psutil.cpu_percent(interval=None)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        with (
            self.docker_output_path.open("w", newline="", encoding="utf-8") as docker_file,
            self.host_output_path.open("w", newline="", encoding="utf-8") as host_file,
        ):
            docker_writer = csv.DictWriter(
                docker_file,
                fieldnames=[
                    "timestamp",
                    "node",
                    "container",
                    "cpu_percent",
                    "memory_percent",
                    "memory_used",
                    "memory_limit",
                    "network_in",
                    "network_out",
                    "block_in",
                    "block_out",
                    "pids",
                ],
            )

            host_writer = csv.DictWriter(
                host_file,
                fieldnames=[
                    "timestamp",
                    "node",
                    "cpu_percent",
                    "memory_percent",
                    "memory_used_bytes",
                    "memory_total_bytes",
                    "load_1m",
                    "load_5m",
                    "load_15m",
                    "disk_read_bytes",
                    "disk_write_bytes",
                    "network_bytes_sent",
                    "network_bytes_recv",
                ],
            )

            docker_writer.writeheader()
            host_writer.writeheader()

            while not self._stop_event.is_set():
                timestamp = datetime.now(timezone.utc).isoformat()

                for row in self._collect_docker_stats(timestamp):
                    docker_writer.writerow(row)

                host_writer.writerow(self._collect_host_stats(timestamp))

                docker_file.flush()
                host_file.flush()

                time.sleep(self.interval_seconds)

    def _collect_docker_stats(self, timestamp: str) -> list[dict]:
        command = [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "{{json .}}",
        ]

        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if result.returncode != 0:
            return []

        rows = []

        for line in result.stdout.splitlines():
            if not line.strip():
                continue

            try:
                stats = json.loads(line)
            except json.JSONDecodeError:
                continue

            memory_used, memory_limit = split_pair(stats.get("MemUsage", ""))
            network_in, network_out = split_pair(stats.get("NetIO", ""))
            block_in, block_out = split_pair(stats.get("BlockIO", ""))

            rows.append(
                {
                    "timestamp": timestamp,
                    "node": self.node_name,
                    "container": stats.get("Name", ""),
                    "cpu_percent": clean_percent(stats.get("CPUPerc", "")),
                    "memory_percent": clean_percent(stats.get("MemPerc", "")),
                    "memory_used": memory_used,
                    "memory_limit": memory_limit,
                    "network_in": network_in,
                    "network_out": network_out,
                    "block_in": block_in,
                    "block_out": block_out,
                    "pids": stats.get("PIDs", ""),
                }
            )

        return rows

    def _collect_host_stats(self, timestamp: str) -> dict:
        memory = psutil.virtual_memory()
        disk_io = psutil.disk_io_counters()
        network_io = psutil.net_io_counters()

        load_1m, load_5m, load_15m = get_load_average()

        return {
            "timestamp": timestamp,
            "node": self.node_name,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": memory.percent,
            "memory_used_bytes": memory.used,
            "memory_total_bytes": memory.total,
            "load_1m": load_1m,
            "load_5m": load_5m,
            "load_15m": load_15m,
            "disk_read_bytes": disk_io.read_bytes if disk_io else "",
            "disk_write_bytes": disk_io.write_bytes if disk_io else "",
            "network_bytes_sent": network_io.bytes_sent if network_io else "",
            "network_bytes_recv": network_io.bytes_recv if network_io else "",
        }


def clean_percent(value: str) -> str:
    return value.replace("%", "").strip()


def split_pair(value: str) -> tuple[str, str]:
    if "/" not in value:
        return value.strip(), ""

    left, right = value.split("/", 1)
    return left.strip(), right.strip()


def get_load_average() -> tuple[float | str, float | str, float | str]:
    try:
        return psutil.getloadavg()
    except (AttributeError, OSError):
        return "", "", ""
