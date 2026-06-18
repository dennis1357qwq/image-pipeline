import os
import psycopg

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


class PostgresJobRepository:
    def __init__(self) -> None:
        self.connection_info = {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "dbname": os.getenv("POSTGRES_DB", "image_pipeline"),
            "user": os.getenv("POSTGRES_USER", "postgres"),
            "password": os.getenv("POSTGRES_PASSWORD", "postgres"),
        }

    def _connect(self):
        return psycopg.connect(**self.connection_info)

    def create_job(
        self,
        job_id: str,
        operation: str,
        input_key: str,
        output_key: str,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (
                        job_id,
                        operation,
                        input_key,
                        output_key,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (job_id, operation, input_key, output_key, "PENDING"),
                )

    def get_job(self, job_id: str) -> JobMetadata:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_id, operation, input_key, output_key
                    FROM jobs
                    WHERE job_id = %s
                    """,
                    (job_id,),
                )
                row = cur.fetchone()

        if row is None:
            raise ValueError(f"Job not found: {job_id}")

        return JobMetadata(
            job_id=row[0],
            operation=row[1],
            input_key=row[2],
            output_key=row[3],
        )

    def mark_processing(self, job_id: str) -> None:
        self._update_status(job_id, "PROCESSING")

    def mark_done(self, job_id: str) -> None:
        self._update_status(job_id, "DONE")

    def mark_failed(self, job_id: str) -> None:
        self._update_status(job_id, "FAILED")

    def _update_status(self, job_id: str, status: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE jobs
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = %s
                    """,
                    (status, job_id),
                )