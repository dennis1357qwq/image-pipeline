import json
import os
import uuid
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Response
from redis.exceptions import RedisError

from image_pipeline_common.job_repository import PostgresJobRepository
from image_pipeline_common.models import PipelineStep
from image_pipeline_common.queue_client import RedisQueueClient
from image_pipeline_common.storage_client import ObjectStorageClient


app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = ObjectStorageClient()
job_repository = PostgresJobRepository()
queue = RedisQueueClient()

MAX_QUEUE_LENGTH = int(os.getenv("MAX_QUEUE_LENGTH", "100"))

logger = logging.getLogger(__name__)


@app.get("/health")
def health():
    return {"status": "ok"}


def parse_pipeline(pipeline_json: str) -> list[PipelineStep]:
    allowed_operations = {
        "grayscale",
        "thumbnail",
        "blur",
        "rotate",
        "face_blur",
        "sharpen",
        "contrast",
        "emboss",
        "edge_detect",
    }

    try:
        raw_pipeline = json.loads(pipeline_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Pipeline must be valid JSON")

    if not isinstance(raw_pipeline, list) or len(raw_pipeline) == 0:
        raise HTTPException(
            status_code=400,
            detail="Pipeline must be a non-empty list",
        )

    pipeline: list[PipelineStep] = []

    for step in raw_pipeline:
        if not isinstance(step, dict):
            raise HTTPException(
                status_code=400,
                detail="Each pipeline step must be an object",
            )

        operation = step.get("operation")
        parameters = step.get("parameters", {})

        if operation not in allowed_operations:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown operation: {operation}",
            )

        if not isinstance(parameters, dict):
            raise HTTPException(
                status_code=400,
                detail="Pipeline step parameters must be an object",
            )

        pipeline.append(
            PipelineStep(
                operation=operation,
                parameters=parameters,
            )
        )

    return pipeline


def pipeline_to_response(pipeline: list[PipelineStep]) -> list[dict]:
    return [
        {
            "operation": step.operation,
            "parameters": step.parameters,
        }
        for step in pipeline
    ]


@app.post("/jobs")
async def create_job(
    pipeline: str = Form(...),
    file: UploadFile = File(...),
):
    parsed_pipeline = parse_pipeline(pipeline)

    if queue.length() >= MAX_QUEUE_LENGTH:
        raise HTTPException(
            status_code=429,
            detail="Queue capacity reached. Please retry later.",
        )

    job_id = str(uuid.uuid4())
    input_key = f"originals/{job_id}/{file.filename}"
    output_key = f"results/{job_id}/result.png"

    image_bytes = await file.read()

    storage.upload(
        key=input_key,
        data=image_bytes,
    )

    job_repository.create_job(
        job_id=job_id,
        pipeline=parsed_pipeline,
        input_key=input_key,
        output_key=output_key,
    )

    try:
        queue.push_job(job_id)
    except RedisError:
        job_repository.mark_failed(job_id)
        logger.exception("Failed to enqueue job %s", job_id)

        raise HTTPException(
            status_code=503,
            detail="Job could not be queued. Please retry later.",
        )

    return {
        "job_id": job_id,
        "status": "PENDING",
        "pipeline": pipeline_to_response(parsed_pipeline),
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        metadata = job_repository.get_job(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": metadata.job_id,
        "pipeline": pipeline_to_response(metadata.pipeline),
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