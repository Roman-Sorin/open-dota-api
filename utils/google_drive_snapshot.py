from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
from typing import Any


class GoogleDriveSnapshotManager:
    def __init__(
        self,
        *,
        service_account_json: str,
        folder_id: str,
        snapshot_name: str,
        local_db_path: Path,
        min_upload_interval_seconds: int = 60,
    ) -> None:
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Google Drive snapshot support requires the optional Google API dependencies."
            ) from exc

        service_account_info = self._parse_service_account_json(service_account_json)
        credentials = Credentials.from_service_account_info(
            service_account_info,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self._folder_id = folder_id
        self._snapshot_name = snapshot_name
        self._local_db_path = local_db_path
        self._meta_path = local_db_path.with_suffix(f"{local_db_path.suffix}.gdrive-meta.json")
        self._min_upload_interval_seconds = max(int(min_upload_interval_seconds), 0)

    def restore_if_available(self) -> bool:
        remote = self._find_snapshot_file()
        if remote is None:
            return False
        from googleapiclient.http import MediaIoBaseDownload

        self._local_db_path.parent.mkdir(parents=True, exist_ok=True)
        request = self._service.files().get_media(fileId=remote["id"])
        with io.FileIO(self._local_db_path, mode="wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        self._write_meta(
            {
                "file_id": str(remote["id"]),
                "last_uploaded_at": datetime.now(tz=timezone.utc).isoformat(),
                "snapshot_name": self._snapshot_name,
            }
        )
        return True

    def sync_if_due(self, *, force: bool = False) -> bool:
        if not self._local_db_path.exists():
            return False
        if not force and not self._upload_is_due():
            return False

        from googleapiclient.http import MediaFileUpload

        file_id = self._current_file_id()
        media = MediaFileUpload(str(self._local_db_path), mimetype="application/x-sqlite3", resumable=True)
        if file_id:
            response = self._service.files().update(fileId=file_id, media_body=media).execute()
        else:
            metadata = {"name": self._snapshot_name, "parents": [self._folder_id]}
            response = self._service.files().create(body=metadata, media_body=media, fields="id").execute()
        self._write_meta(
            {
                "file_id": str(response["id"]),
                "last_uploaded_at": datetime.now(tz=timezone.utc).isoformat(),
                "snapshot_name": self._snapshot_name,
            }
        )
        return True

    def _find_snapshot_file(self) -> dict[str, Any] | None:
        safe_name = self._snapshot_name.replace("'", "\\'")
        query = f"'{self._folder_id}' in parents and trashed = false and name = '{safe_name}'"
        response = self._service.files().list(
            q=query,
            spaces="drive",
            fields="files(id,name,modifiedTime)",
            pageSize=1,
            orderBy="modifiedTime desc",
        ).execute()
        files = response.get("files") or []
        return files[0] if files else None

    def _upload_is_due(self) -> bool:
        meta = self._read_meta()
        last_uploaded_at = str(meta.get("last_uploaded_at") or "")
        if not last_uploaded_at:
            return True
        try:
            last_dt = datetime.fromisoformat(last_uploaded_at)
        except ValueError:
            return True
        elapsed = (datetime.now(tz=timezone.utc) - last_dt).total_seconds()
        return elapsed >= self._min_upload_interval_seconds

    def _current_file_id(self) -> str | None:
        meta = self._read_meta()
        file_id = str(meta.get("file_id") or "")
        if file_id:
            return file_id
        remote = self._find_snapshot_file()
        return str(remote["id"]) if remote else None

    def _read_meta(self) -> dict[str, Any]:
        if not self._meta_path.exists():
            return {}
        try:
            return json.loads(self._meta_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _write_meta(self, payload: dict[str, Any]) -> None:
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)
        self._meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _parse_service_account_json(service_account_json: str) -> dict[str, Any]:
        try:
            parsed = json.loads(service_account_json)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        normalized = service_account_json.strip()
        key_match = re.search(
            r'"private_key"\s*:\s*"(?P<value>.*?)"\s*,\s*"client_email"',
            normalized,
            re.DOTALL,
        )
        if not key_match:
            raise

        key_value = key_match.group("value")
        repaired_key_value = key_value.replace("\r\n", "\n").replace("\n", "\\n")
        repaired = (
            normalized[: key_match.start("value")]
            + repaired_key_value
            + normalized[key_match.end("value") :]
        )
        parsed = json.loads(repaired)
        if not isinstance(parsed, dict):
            raise ValueError("Google Drive service-account secret did not parse to an object.")
        return parsed
