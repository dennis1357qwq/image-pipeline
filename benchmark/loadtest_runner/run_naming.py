from datetime import datetime


def format_rate(rate: float) -> str:
    if float(rate).is_integer():
        return str(int(rate))

    return str(rate).replace(".", "p")


def build_run_name(
    *,
    timestamp: str,
    environment: str,
    profile: str,
    rate: float,
    duration: str,
    total_nodes: int,
    heavy_workers: int,
    default_workers: int,
    run_id: str | None = None,
) -> str:
    parts = [
        f"{total_nodes}-node",
        environment,
        f"{heavy_workers}h",
        f"{default_workers}d-worker",
        f"{format_rate(rate)}rps",
        duration,
        profile,
        timestamp,
    ]

    if run_id:
        parts.append(run_id)

    return "-".join(parts)


def timestamp_for_run_name() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
