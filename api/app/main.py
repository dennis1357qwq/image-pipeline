import json
import os
import uuid
import logging
import hashlib

from fastapi import FastAPI, File, Header, Form, HTTPException, UploadFile, Response
from redis.exceptions import RedisError
from psycopg.errors import UniqueViolation

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

HEAVY_REPEAT_THRESHOLD = 5

OPERATION_COSTS = {
    "rotate": 1,
    "grayscale": 1,
    "thumbnail": 4,
    "emboss": 4,
    "contrast": 4,
    "edge_detect": 6,
    "sharpen": 7,
    "blur": 10,
}

HEAVY_COST_THRESHOLD = 40

def is_heavy_pipeline(pipeline: list[PipelineStep]) -> bool:
    total_cost = 0.0

    for step in pipeline:
        operation = step.operation
        parameters = step.parameters or {}

        try:
            repeat = max(1, int(parameters.get("repeat", 1)))
        except (TypeError, ValueError):
            repeat = 1

        operation_cost = OPERATION_COSTS.get(operation, 1)

        if parameters.get("region") is not None:
            operation_cost *= 0.2

        total_cost += operation_cost * repeat

    return total_cost >= HEAVY_COST_THRESHOLD


def log_event(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)

def build_idempotency_request_hash(
    pipeline: list[PipelineStep],
    image_bytes: bytes,
) -> str:
    payload = {
        "pipeline": [
            {
                "operation": step.operation,
                "parameters": step.parameters,
            }
            for step in pipeline
        ],
        "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
    }

    encoded_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded_payload).hexdigest()


@app.get("/health")
def health():
    return {"status": "ok"}


def parse_pipeline(pipeline_json: str) -> list[PipelineStep]:
    allowed_operations = {
        "grayscale",
        "thumbnail",
        "blur",
        "rotate",
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    parsed_pipeline = parse_pipeline(pipeline)
    image_bytes = await file.read()

    idempotency_request_hash = None

    if idempotency_key:
        idempotency_request_hash = build_idempotency_request_hash(
            pipeline=parsed_pipeline,
            image_bytes=image_bytes,
        )

        existing_entry = job_repository.get_job_by_idempotency_key(idempotency_key)

        if existing_entry:
            existing, existing_request_hash = existing_entry

            if existing_request_hash != idempotency_request_hash:
                log_event("idempotency_conflict",idempotency_key=idempotency_key)
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used for a different request.",
                )
            log_event(
                "idempotency_hit",
                idempotency_key=idempotency_key,
                job_id=existing.job_id,
                status=existing.status,
            )
            return {
                "job_id": existing.job_id,
                "status": existing.status,
                "pipeline": pipeline_to_response(existing.pipeline),
            }

    target_queue = "jobs:heavy" if is_heavy_pipeline(parsed_pipeline) else "jobs:default"

    queue_length = queue.length(target_queue)

    if queue_length >= MAX_QUEUE_LENGTH:
        log_event(
            "job_rejected_429",
            target_queue=target_queue,
            queue_length=queue_length,
            max_queue_length=MAX_QUEUE_LENGTH,
        )
        raise HTTPException(
            status_code=429,
            detail="Queue capacity reached. Please retry later.",
        )

    job_id = str(uuid.uuid4())
    input_key = f"originals/{job_id}/{file.filename}"
    output_key = f"results/{job_id}/result.png"

    storage.upload(key=input_key, data=image_bytes)

    try:
        job_repository.create_job(
            job_id=job_id,
            pipeline=parsed_pipeline,
            input_key=input_key,
            output_key=output_key,
            idempotency_key=idempotency_key,
            idempotency_request_hash=idempotency_request_hash,
        )
    except UniqueViolation:
        if not idempotency_key:
            raise

        existing_entry = job_repository.get_job_by_idempotency_key(idempotency_key)

        if existing_entry is None:
            raise

        existing, existing_request_hash = existing_entry

        if existing_request_hash != idempotency_request_hash:
            log_event("idempotency_conflict",idempotency_key=idempotency_key)
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key was already used for a different request.",
            )
        log_event(
            "idempotency_hit",
            idempotency_key=idempotency_key,
            job_id=existing.job_id,
            status=existing.status,
        )
        return {
            "job_id": existing.job_id,
            "status": existing.status,
            "pipeline": pipeline_to_response(existing.pipeline),
        }

    try:
        queue.push_job(job_id, queue_name=target_queue)
    except RedisError:
        job_repository.mark_failed(job_id)
        logger.exception("Failed to enqueue job %s", job_id)
        raise HTTPException(
            status_code=503,
            detail="Job could not be queued. Please retry later.",
        )
    log_event(
        "job_created",
        job_id=job_id,
        target_queue=target_queue,
        queue_length_at_submit=queue_length,
        pipeline=pipeline_to_response(parsed_pipeline),
        idempotency_key_present=idempotency_key is not None,
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
