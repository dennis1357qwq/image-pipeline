from io import BytesIO

from PIL import Image

from app.image_processor import process_image
from app.job_repository import LocalJobRepository
from app.queue_client import LocalQueueClient, RedisQueueClient
from app.storage_client import LocalStorageClient


class Worker:
    def __init__(self, queue, job_repository, storage):
        self.queue = queue
        self.job_repository = job_repository
        self.storage = storage

    def run_once(self) -> None:
        job = self.queue.get_next_job()
        print(f"Picked job: {job.job_id}")

        metadata = self.job_repository.get_job(job.job_id)
        print(f"Loaded metadata: {metadata}")

        input_bytes = self.storage.download(metadata.input_key)

        with Image.open(BytesIO(input_bytes)) as image:
            result_image = process_image(image=image, operation=metadata.operation)

        output_buffer = BytesIO()
        result_image.save(output_buffer, format="PNG")

        self.storage.upload(key=metadata.output_key, data=output_buffer.getvalue())

        self.job_repository.mark_done(job.job_id)
        print(f"Finished job: {job.job_id}")

    def run_forever(self) -> None:
        while True:
            self.run_once()


if __name__ == "__main__":
    worker = Worker(
        queue=RedisQueueClient(),
        job_repository=LocalJobRepository(),
        storage=LocalStorageClient(),
    )
    worker.run_forever()