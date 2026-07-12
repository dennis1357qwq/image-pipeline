import subprocess
import shlex
from pathlib import Path

from benchmark.loadtest_runner.node_config import NodeConfig


class SSHClient:
    def __init__(self, node: NodeConfig):
        self.node = node

    @property
    def destination(self) -> str:
        return f"{self.node.ssh_user}@{self.node.host}"

    def check_connection(self, timeout_seconds: int = 10) -> bool:
        command = self._ssh_base_command() + [
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={timeout_seconds}",
            "true",
        ]

        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        return result.returncode == 0

    def run(
        self,
        remote_command: str,
        *,
        check: bool = True,
        timeout_seconds: int | None = None,
    ) -> subprocess.CompletedProcess:
        command = self._ssh_base_command() + [remote_command]

        return subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
            timeout=timeout_seconds,
        )

    def start_background(
        self,
        remote_command: str,
        stdout_path: str,
        stderr_path: str,
    ) -> int:
        wrapped_command = (
            f"nohup sh -c {shlex.quote(remote_command)} "
            f"> {shlex.quote(stdout_path)} "
            f"2> {shlex.quote(stderr_path)} "
            f"< /dev/null & echo $!"
        )

        result = self.run(wrapped_command)

        pid_text = result.stdout.strip()

        if not pid_text.isdigit():
            raise RuntimeError(
                f"Could not parse remote PID from node '{self.node.name}': "
                f"{result.stdout!r}"
            )

        return int(pid_text)

    def stop_process(self, pid: int, signal_name: str = "TERM") -> None:
        self.run(
            f"kill -{signal_name} {pid}",
            check=False,
        )

    def create_directory(self, remote_path: str) -> None:
        self.run(f"mkdir -p {remote_path}")

    def download_file(
        self,
        remote_path: str,
        local_path: Path,
    ) -> None:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            "scp",
            "-P",
            str(self.node.ssh_port),
            f"{self.destination}:{remote_path}",
            str(local_path),
        ]

        subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
    ) -> None:
        command = [
            "scp",
            "-P",
            str(self.node.ssh_port),
            str(local_path),
            f"{self.destination}:{remote_path}",
        ]

        subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )

    def _ssh_base_command(self) -> list[str]:
        return [
            "ssh",
            "-p",
            str(self.node.ssh_port),
            self.destination,
        ]
