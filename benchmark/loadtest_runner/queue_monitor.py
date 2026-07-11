import csv
import threading
from datetime import datetime, timezone
from pathlib import Path

import redis


class QueueMonitor:
    def __init__(
        self,
        output_path: Path,
        node_name: str,
        redis_url: str,
        interval_seconds: float = 1.0,
    ):
        self.output_path = Path(output_path)
        self.node_name = node_name
        self.redis = redis.Redis.from_url(redis_url)
        self.interval_seconds = interval_seconds

        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join()

    def _run(self) -> None:
        fieldnames = [
            "timestamp",
            "node",
            "default_queue_length",
            "heavy_queue_length",
        ]

        with self.output_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()

            while not self._stop_event.is_set():
                timestamp = datetime.now(timezone.utc).isoformat()

                try:
                    default_length = self.redis.llen("jobs:default")
                    heavy_length = self.redis.llen("jobs:heavy")
                except redis.RedisError:
                    default_length = ""
                    heavy_length = ""

                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "node": self.node_name,
                        "default_queue_length": default_length,
                        "heavy_queue_length": heavy_length,
                    }
                )
                file.flush()

                self._stop_event.wait(self.interval_seconds)