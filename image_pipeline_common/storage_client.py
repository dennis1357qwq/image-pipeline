import os
from io import BytesIO
from pathlib import Path

import boto3


class LocalStorageClient:
    def download(self, key: str) -> bytes:
        return Path(key).read_bytes()

    def upload(self, key: str, data: bytes) -> None:
        Path(key).parent.mkdir(parents=True, exist_ok=True)
        Path(key).write_bytes(data)


class ObjectStorageClient:
    def __init__(self) -> None:
        self.bucket_name = os.getenv("OBJECT_STORAGE_BUCKET", "image-pipeline")

        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("OBJECT_STORAGE_ENDPOINT", "http://localhost:9000"),
            aws_access_key_id=os.getenv("OBJECT_STORAGE_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("OBJECT_STORAGE_SECRET_KEY", "minioadmin"),
        )

    def download(self, key: str) -> bytes:
        response = self.client.get_object(
            Bucket=self.bucket_name,
            Key=key,
        )
        return response["Body"].read()

    def upload(self, key: str, data: bytes) -> None:
        self.client.upload_fileobj(
            Fileobj=BytesIO(data),
            Bucket=self.bucket_name,
            Key=key,
        )