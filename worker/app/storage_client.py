from pathlib import Path

class LocalStorageClient:
    def download(self, key: str) -> bytes:
        return Path(key).read_bytes()

    def upload(self, key: str, data: bytes) -> None:
        Path(key).parent.mkdir(parents=True, exist_ok=True)
        Path(key).write_bytes(data)