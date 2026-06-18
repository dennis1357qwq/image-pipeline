from io import BytesIO

from PIL import Image

from app.image_processor import process_image
from app.job_repository import LocalJobRepository, PostgresJobRepository
from app.queue_client import LocalQueueClient, RedisQueueClient
from app.storage_client import LocalStorageClient, ObjectStorageClient


class Worker:
    def __init__(self, queue, job_repository, storage):
        self.queue = queue
        self.job_repository = job_repository
        self.storage = storage

    def run_once(self) -> None:
        job = self.queue.get_next_job()
        print(f"Picked job: {job.job_id}")

        try:
            metadata = self.job_repository.get_job(job.job_id)
            print(f"Loaded metadata: {metadata}")

            self.job_repository.mark_processing(job.job_id)

            input_bytes = self.storage.download(metadata.input_key)

            with Image.open(BytesIO(input_bytes)) as image:
                result_image = process_image(image=image, operation=metadata.operation)

            output_buffer = BytesIO()
            result_image.save(output_buffer, format="PNG")

            self.storage.upload(key=metadata.output_key, data=output_buffer.getvalue())

            self.job_repository.mark_done(job.job_id)
            print(f"Finished job: {job.job_id}")

        except Exception as error:
            print(f"Failed job: {job.job_id}, error: {error}")
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