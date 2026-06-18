from app.models import JobMetadata


class LocalJobRepository:
    def get_job(self, job_id: str) -> JobMetadata:
        operations = {
            "job-1": "grayscale",
            "job-2": "thumbnail",
            "job-3": "blur",
            "job-4": "grayscale",
            "job-5": "blur",
        }

        operation = operations.get(job_id, "grayscale")

        return JobMetadata(
            job_id=job_id,
            operation=operation,
            input_key="originals/job-1/input.png",
            output_key=f"results/{job_id}/{operation}.png",
        )

    def mark_done(self, job_id: str) -> None:
        print(f"{job_id} finished")