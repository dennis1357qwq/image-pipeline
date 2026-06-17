from app.models import JobMetadata

class LocalJobRepository:
    def get_job(self, job_id: str) -> JobMetadata:
        return JobMetadata(
            job_id=job_id,
            operation="grayscale",
            input_key="examples/test.png",
            output_key="output/result.png",
        )

    def mark_done(self, job_id: str) -> None:
        print(f"{job_id} finished")