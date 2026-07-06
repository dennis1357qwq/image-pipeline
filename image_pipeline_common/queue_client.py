import os
import redis

from image_pipeline_common.models import Job
from redis.exceptions import TimeoutError as RedisTimeoutError


class LocalQueueClient:
    def get_next_job(self) -> Job:
        return Job(job_id="job-1")


class RedisQueueClient:
    def __init__(self) -> None:
        self.redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
        )
        self.queue_name = os.getenv("REDIS_QUEUE_NAME", "jobs")

    def get_next_job(self) -> Job | None:
        try:
            result = self.redis.brpop(self.queue_name, timeout=5)
        except RedisTimeoutError:
            return None

        if result is None:
            return None

        _, job_id = result
        return Job(job_id=job_id)

    def push_job(self, job_id: str, queue_name: str | None = None) -> None:
        target = queue_name or self.queue_name
        self.redis.lpush(target, job_id)

    def length(self, queue_name: str | None = None) -> int:
        target = queue_name or self.queue_name
        return self.redis.llen(target)
    
    def memory_info(self) -> dict:
        return self.redis.info("memory")