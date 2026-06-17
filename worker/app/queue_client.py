from app.models import Job

class LocalQueueClient:
    def get_next_job(self) -> Job:
        return Job(job_id="job-1")