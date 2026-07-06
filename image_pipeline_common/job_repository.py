import os
import psycopg

from image_pipeline_common.models import JobMetadata, PipelineStep
from psycopg.types.json import Json


def _pipeline_to_json(pipeline: list[PipelineStep]) -> list[dict]:
    return [
        {
            "operation": step.operation,
            "parameters": step.parameters,
        }
        for step in pipeline
    ]


def _pipeline_from_json(data: list[dict]) -> list[PipelineStep]:
    return [
        PipelineStep(
            operation=item["operation"],
            parameters=item.get("parameters", {}),
        )
        for item in data
    ]


class LocalJobRepository:
    def get_job(self, job_id: str) -> JobMetadata:
        pipeline = [
            PipelineStep(
                operation="grayscale",
                parameters={},
            )
        ]

        return JobMetadata(
            job_id=job_id,
            pipeline=pipeline,
            input_key="originals/job-1/input.png",
            output_key=f"results/{job_id}/result.png",
            status="PENDING",
        )

    def mark_processing(self, job_id: str) -> None:
        print(f"{job_id} processing")

    def mark_done(self, job_id: str) -> None:
        print(f"{job_id} finished")

    def mark_failed(self, job_id: str) -> None:
        print(f"{job_id} failed")


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
        pipeline: list[PipelineStep],
        input_key: str,
        output_key: str,
        idempotency_key: str | None = None,
        idempotency_request_hash: str | None = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO jobs (
                        job_id,
                        idempotency_key,
                        idempotency_request_hash,
                        pipeline,
                        input_key,
                        output_key,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        idempotency_key,
                        idempotency_request_hash,
                        Json(_pipeline_to_json(pipeline)),
                        input_key,
                        output_key,
                        "PENDING",
                    ),
                )

    def get_job_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> tuple[JobMetadata, str | None] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_id, pipeline, input_key, output_key, status, idempotency_request_hash, created_at
                    FROM jobs
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                )
                row = cur.fetchone()

        if row is None:
            return None

        metadata = JobMetadata(
            job_id=row[0],
            pipeline=_pipeline_from_json(row[1]),
            input_key=row[2],
            output_key=row[3],
            status=row[4],
            created_at=[5],
        )

        return metadata, row[5]

    def get_job(self, job_id: str) -> JobMetadata:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_id, pipeline, input_key, output_key, status, created_at
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
            pipeline=_pipeline_from_json(row[1]),
            input_key=row[2],
            output_key=row[3],
            status=row[4],
            created_at=row[5],
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