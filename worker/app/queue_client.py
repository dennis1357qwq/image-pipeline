import os
import redis

from app.models import Job


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

    def get_next_job(self) -> Job:
        _, job_id = self.redis.brpop(self.queue_name)
        return Job(job_id=job_id)

    def push_job(self, job_id: str) -> None:
        self.redis.lpush(self.queue_name, job_id)