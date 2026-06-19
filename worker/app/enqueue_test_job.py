from image_pipeline_common.queue_client import RedisQueueClient

if __name__ == "__main__":
    queue = RedisQueueClient()

    for i in range(1, 6):
        job_id = f"job-{i}"
        queue.push_job(job_id)
        print(f"Enqueued {job_id}")