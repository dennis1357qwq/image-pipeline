import os
import uuid
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Response
from redis.exceptions import RedisError

from image_pipeline_common.job_repository import PostgresJobRepository
from image_pipeline_common.queue_client import RedisQueueClient
from image_pipeline_common.storage_client import ObjectStorageClient


app = FastAPI()

storage = ObjectStorageClient()
job_repository = PostgresJobRepository()
queue = RedisQueueClient()

MAX_QUEUE_LENGTH = int(os.getenv("MAX_QUEUE_LENGTH", "100"))

logger = logging.getLogger(__name__)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs")
async def create_job(
    operation: str = Form(...),
    file: UploadFile = File(...),
):
    allowed_operations = {"grayscale", "thumbnail", "blur"}

    if operation not in allowed_operations:
        raise HTTPException(status_code=400, detail="Unknown operation")
    
    if queue.length() >= MAX_QUEUE_LENGTH:
        raise HTTPException(
            status_code=429,
            detail="Queue capacity reached. Please retry later.",
        )

    job_id = str(uuid.uuid4())
    input_key = f"originals/{job_id}/{file.filename}"
    output_key = f"results/{job_id}/{operation}.png"

    image_bytes = await file.read()

    storage.upload(
        key=input_key,
        data=image_bytes,
    )

    job_repository.create_job(
        job_id=job_id,
        operation=operation,
        input_key=input_key,
        output_key=output_key,
    )

    try:
        queue.push_job(job_id)
    except RedisError as error:
        job_repository.mark_failed(job_id)
        logger.exception("Failed to enqueue job %s", job_id)

        raise HTTPException(
            status_code=503,
            detail="Job could not be queued. Please retry later.",
        )

    return {
        "job_id": job_id,
        "status": "PENDING",
        "operation": operation,
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        metadata = job_repository.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": metadata.job_id,
        "operation": metadata.operation,
        "input_key": metadata.input_key,
        "output_key": metadata.output_key,
        "status": metadata.status,
    }

@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str):
    try:
        metadata = job_repository.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")

    if metadata.status != "DONE":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not done yet: {metadata.status}",
        )

    image_bytes = storage.download(metadata.output_key)

    return Response(
        content=image_bytes,
        media_type="image/png",
    )