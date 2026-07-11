import argparse
import signal
import threading
from pathlib import Path

from benchmark.loadtest_runner.docker_monitor import DockerMonitor


def parse_args():
    parser = argparse.ArgumentParser(
        description="Collect Docker and host metrics on one node."
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where host_stats.csv and docker_stats.csv are written.",
    )
    parser.add_argument(
        "--node-name",
        required=True,
        help="Logical node name written into every metrics row.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=1.0,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    monitor = DockerMonitor(
        docker_output_path=output_dir / "docker_stats.csv",
        host_output_path=output_dir / "host_stats.csv",
        node_name=args.node_name,
        interval_seconds=args.interval_seconds,
    )

    stop_event = threading.Event()

    def handle_stop_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)

    monitor.start()

    try:
        stop_event.wait()
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()