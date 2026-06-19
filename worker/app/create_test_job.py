from pathlib import Path
import uuid

from image_pipeline_common.job_repository import PostgresJobRepository
from image_pipeline_common.queue_client import RedisQueueClient
from image_pipeline_common.storage_client import ObjectStorageClient


if __name__ == "__main__":
    job_id = str(uuid.uuid4())
    operation = "grayscale"

    input_key = f"originals/{job_id}/input.png"
    output_key = f"results/{job_id}/{operation}.png"

    image_path = Path("examples/test.png")

    storage = ObjectStorageClient()
    repository = PostgresJobRepository()
    queue = RedisQueueClient()

    storage.upload(input_key, image_path.read_bytes())

    repository.create_job(
        job_id=job_id,
        operation=operation,
        input_key=input_key,
        output_key=output_key,
    )

    queue.push_job(job_id)

    print(f"Created and enqueued {job_id}")