from __future__ import annotations

import json
from pathlib import Path

from utils.google_drive_snapshot import GoogleDriveSnapshotManager


def test_parse_service_account_json_accepts_literal_newlines_in_private_key() -> None:
    raw_secret = """{
  "type": "service_account",
  "project_id": "turbo-buff-storage",
  "private_key_id": "abc",
  "private_key": "-----BEGIN PRIVATE KEY-----
line-one
line-two
-----END PRIVATE KEY-----
",
  "client_email": "turbo-buff-drive@turbo-buff-storage.iam.gserviceaccount.com"
}"""

    parsed = GoogleDriveSnapshotManager._parse_service_account_json(raw_secret)

    assert parsed["type"] == "service_account"
    assert parsed["client_email"] == "turbo-buff-drive@turbo-buff-storage.iam.gserviceaccount.com"
    assert "-----BEGIN PRIVATE KEY-----\nline-one\nline-two\n-----END PRIVATE KEY-----\n" == parsed["private_key"]


def _manager_for_guard(tmp_path: Path, *, local_size: int, meta: dict[str, object]) -> GoogleDriveSnapshotManager:
    local_db = tmp_path / "matches.sqlite3"
    local_db.write_bytes(b"x" * local_size)
    meta_path = local_db.with_suffix(".sqlite3.gdrive-meta.json")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    manager = GoogleDriveSnapshotManager.__new__(GoogleDriveSnapshotManager)
    manager._local_db_path = local_db
    manager._meta_path = meta_path
    manager._snapshot_name = "matches.sqlite3"
    return manager


def test_snapshot_guard_blocks_stale_worker_from_overwriting_larger_drive_recovery(tmp_path: Path) -> None:
    manager = _manager_for_guard(tmp_path, local_size=10_000_000, meta={"file_id": "drive-file"})

    blocked = manager._remote_snapshot_must_not_be_overwritten(
        {"id": "drive-file", "modifiedTime": "2026-07-20T18:00:00Z", "size": "100000000", "md5Checksum": "abc"}
    )

    assert blocked is True
    saved = json.loads(manager._meta_path.read_text(encoding="utf-8"))
    assert "materially larger" in saved["upload_blocked_reason"]
    assert saved["remote_size_bytes"] == 100_000_000


def test_snapshot_guard_blocks_remote_generation_changed_outside_app(tmp_path: Path) -> None:
    manager = _manager_for_guard(
        tmp_path,
        local_size=100_000_000,
        meta={"file_id": "drive-file", "remote_modified_time": "2026-07-20T17:00:00Z"},
    )

    blocked = manager._remote_snapshot_must_not_be_overwritten(
        {"id": "drive-file", "modifiedTime": "2026-07-20T18:00:00Z", "size": "100000000", "md5Checksum": "abc"}
    )

    assert blocked is True
    saved = json.loads(manager._meta_path.read_text(encoding="utf-8"))
    assert "changed outside this app" in saved["upload_blocked_reason"]
