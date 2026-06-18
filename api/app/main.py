import os
import uuid
from io import BytesIO

import boto3
import psycopg
import redis
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Response


app = FastAPI()


OBJECT_STORAGE_BUCKET = os.getenv("OBJECT_STORAGE_BUCKET", "image-pipeline")
REDIS_QUEUE_NAME = os.getenv("REDIS_QUEUE_NAME", "jobs")


s3_client = boto3.client(
    "s3",
    endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT", "http://localhost:9000"),
    aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY", "minioadmin"),
    aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_KEY", "minioadmin"),
)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True,
)


def get_db_connection():
    return psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "image_pipeline"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


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

    job_id = str(uuid.uuid4())
    input_key = f"originals/{job_id}/{file.filename}"
    output_key = f"results/{job_id}/{operation}.png"

    image_bytes = await file.read()

    s3_client.upload_fileobj(
        Fileobj=BytesIO(image_bytes),
        Bucket=OBJECT_STORAGE_BUCKET,
        Key=input_key,
    )

    with get_db_connection() as conn:
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

    redis_client.lpush(REDIS_QUEUE_NAME, job_id)

    return {
        "job_id": job_id,
        "status": "PENDING",
        "operation": operation,
    }


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_id, operation, input_key, output_key, status
                FROM jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": row[0],
        "operation": row[1],
        "input_key": row[2],
        "output_key": row[3],
        "status": row[4],
    }

@app.get("/jobs/{job_id}/result")
def get_job_result(job_id: str):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT output_key, status
                FROM jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")

    output_key, status = row

    if status != "DONE":
        raise HTTPException(status_code=409, detail=f"Job is not done yet: {status}")

    response = s3_client.get_object(
        Bucket=OBJECT_STORAGE_BUCKET,
        Key=output_key,
    )

    image_bytes = response["Body"].read()

    return Response(
        content=image_bytes,
        media_type="image/png",
    )