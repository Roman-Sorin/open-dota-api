from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from typing import Callable

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from utils.config import Settings


class PersistentStoreError(RuntimeError):
    """Raised when durable replica bootstrap or sync fails."""


@dataclass(slots=True)
class S3SqliteReplica:
    bucket: str
    key: str
    local_path: Path
    endpoint_url: str | None = None
    region_name: str | None = None

    def __post_init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=self.region_name,
        )
        self._lock = threading.Lock()

    def bootstrap(self) -> None:
        self.local_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._client.head_object(Bucket=self.bucket, Key=self.key)
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code") or "")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return
            raise PersistentStoreError(f"Unable to inspect remote match-store replica: {exc}") from exc
        except BotoCoreError as exc:
            raise PersistentStoreError(f"Unable to inspect remote match-store replica: {exc}") from exc

        temp_path = self.local_path.with_suffix(f"{self.local_path.suffix}.download")
        try:
            self._client.download_file(self.bucket, self.key, str(temp_path))
            temp_path.replace(self.local_path)
        except (ClientError, BotoCoreError, OSError) as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise PersistentStoreError(f"Unable to download remote match-store replica: {exc}") from exc

    def sync_from_local(self) -> None:
        if not self.local_path.exists():
            return
        with self._lock:
            try:
                self._client.upload_file(str(self.local_path), self.bucket, self.key)
            except (ClientError, BotoCoreError, OSError) as exc:
                raise PersistentStoreError(f"Unable to upload match-store replica: {exc}") from exc


def build_match_store_replica(settings: Settings, db_path: Path) -> S3SqliteReplica | None:
    bucket = (settings.match_store_s3_bucket or "").strip()
    key = (settings.match_store_s3_key or "").strip()
    if not bucket or not key:
        return None
    return S3SqliteReplica(
        bucket=bucket,
        key=key,
        local_path=db_path,
        endpoint_url=settings.match_store_s3_endpoint_url,
        region_name=settings.match_store_s3_region,
    )


def bootstrap_match_store(settings: Settings, db_path: Path) -> tuple[Path, Callable[[], None] | None]:
    replica = build_match_store_replica(settings, db_path)
    if replica is None:
        return db_path, None
    replica.bootstrap()
    return db_path, replica.sync_from_local
