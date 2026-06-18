from pathlib import Path

from app.storage_client import ObjectStorageClient


if __name__ == "__main__":
    storage = ObjectStorageClient()

    local_path = Path("examples/test.png")
    object_key = "originals/job-1/input.png"

    image_bytes = local_path.read_bytes()
    storage.upload(object_key, image_bytes)

    print(f"Uploaded {local_path} to {object_key}")