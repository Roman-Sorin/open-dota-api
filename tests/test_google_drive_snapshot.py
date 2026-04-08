from __future__ import annotations

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
