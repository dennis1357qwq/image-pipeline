import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def retry_with_backoff(
    operation_name: str,
    function: Callable[[], T],
    max_attempts: int = 3,
    base_delay_seconds: float = 0.1,
    max_delay_seconds: float = 1.0,
    log_function: Callable[..., None] | None = None,
) -> T:
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            result = function()

            if attempt > 1 and log_function is not None:
                log_function(
                    "retry_success",
                    operation=operation_name,
                    attempts=attempt,
                )

            return result

        except Exception as error:
            last_error = error

            if attempt == max_attempts:
                if log_function is not None:
                    log_function(
                        "retry_exhausted",
                        operation=operation_name,
                        attempts=attempt,
                        error=str(error),
                    )
                break

            exponential_delay = min(
                max_delay_seconds,
                base_delay_seconds * (2 ** (attempt - 1)),
            )
            delay = random.uniform(0, exponential_delay)

            if log_function is not None:
                log_function(
                    "retry_scheduled",
                    operation=operation_name,
                    attempt=attempt,
                    next_attempt=attempt + 1,
                    delay_ms=round(delay * 1000, 2),
                    error=str(error),
                )

            time.sleep(delay)

    raise last_error