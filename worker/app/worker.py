import json
import os
import time
from io import BytesIO

from PIL import Image
from datetime import datetime, timezone

from app.image_processor import process_image
from image_pipeline_common.job_repository import PostgresJobRepository
from image_pipeline_common.queue_client import RedisQueueClient
from image_pipeline_common.storage_client import ObjectStorageClient

def calculate_queue_wait_time_ms(created_at) -> float | None:
    if created_at is None:
        return None

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)

    return (datetime.now(timezone.utc) - created_at).total_seconds() * 1000

def pipeline_to_log(pipeline) -> list[dict]:
    return [
        {
            "operation": step.operation,
            "parameters": step.parameters,
        }
        for step in pipeline
    ]


def log_event(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


class Worker:
    def __init__(self, queue, job_repository, storage):
        self.queue = queue
        self.job_repository = job_repository
        self.storage = storage
        self.queue_name = os.getenv("REDIS_QUEUE_NAME", "jobs")

    def run_once(self) -> None:
        job = self.queue.get_next_job()

        if job is None:
            return

        total_start = time.perf_counter()

        log_event(
            "job_picked",
            job_id=job.job_id,
            queue_name=self.queue_name,
        )

        try:
            metadata = self.job_repository.get_job(job.job_id)
            queue_wait_time_ms = calculate_queue_wait_time_ms(metadata.created_at)
            self.job_repository.mark_processing(job.job_id)

            download_start = time.perf_counter()
            input_bytes = self.storage.download(metadata.input_key)
            download_time_ms = (time.perf_counter() - download_start) * 1000

            processing_start = time.perf_counter()
            with Image.open(BytesIO(input_bytes)) as image:
                result_image = process_image(image=image, pipeline=metadata.pipeline)
            processing_time_ms = (time.perf_counter() - processing_start) * 1000

            output_buffer = BytesIO()
            result_image.save(output_buffer, format="PNG")

            upload_start = time.perf_counter()
            self.storage.upload(
                key=metadata.output_key,
                data=output_buffer.getvalue(),
            )
            upload_time_ms = (time.perf_counter() - upload_start) * 1000

            self.job_repository.mark_done(job.job_id)

            log_event(
                "job_finished",
                job_id=job.job_id,
                queue_name=self.queue_name,
                status="DONE",
                pipeline=pipeline_to_log(metadata.pipeline),

                queue_wait_time_ms=round(queue_wait_time_ms, 2)
                if queue_wait_time_ms is not None
                else None,

                download_time_ms=round(download_time_ms, 2),
                processing_time_ms=round(processing_time_ms, 2),
                upload_time_ms=round(upload_time_ms, 2),
                total_worker_time_ms=round((time.perf_counter() - total_start) * 1000, 2),
            )

        except Exception as error:
            log_event(
                "job_failed",
                job_id=job.job_id,
                queue_name=self.queue_name,
                status="FAILED",
                error=str(error),
                total_worker_time_ms=round((time.perf_counter() - total_start) * 1000, 2),
            )
            self.job_repository.mark_failed(job.job_id)

    def run_forever(self) -> None:
        while True:
            self.run_once()


if __name__ == "__main__":
    worker = Worker(
        queue=RedisQueueClient(),
        job_repository=PostgresJobRepository(),
        storage=ObjectStorageClient(),
    )
    worker.run_forever()