import subprocess


def run_command(command: list[str]) -> None:
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Cleanup command failed:\n{' '.join(command)}\n{result.stdout}"
        )


def cleanup_local_environment() -> None:
    run_command(
        [
            "docker",
            "exec",
            "image-pipeline-redis",
            "redis-cli",
            "FLUSHDB",
        ]
    )

    run_command(
        [
            "docker",
            "exec",
            "image-pipeline-postgres",
            "psql",
            "-U",
            "postgres",
            "-d",
            "image_pipeline",
            "-c",
            "TRUNCATE TABLE jobs;",
        ]
    )

    run_command(
        [
            "docker",
            "exec",
            "image-pipeline-minio",
            "mc",
            "alias",
            "set",
            "local",
            "http://localhost:9000",
            "minioadmin",
            "minioadmin",
        ]
    )

    run_command(
        [
            "docker",
            "exec",
            "image-pipeline-minio",
            "mc",
            "rm",
            "--recursive",
            "--force",
            "local/image-pipeline/",
        ]
    )

    run_command(
        [
            "docker",
            "exec",
            "image-pipeline-minio",
            "mc",
            "mb",
            "--ignore-existing",
            "local/image-pipeline",
        ]
    )