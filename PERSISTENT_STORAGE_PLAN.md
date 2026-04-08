# Persistent Storage Plan

## Goal

Prevent cached match data from disappearing after Streamlit Cloud reboot, redeploy, or reset.

## Root cause

- Critical cache data was stored only in local `.cache/matches.sqlite3`.
- Streamlit Community Cloud does not guarantee local filesystem persistence across app restarts.

## Chosen solution

- Keep local SQLite as the hot working store inside the Streamlit app instance.
- Use Google Drive as durable snapshot storage for the SQLite file.
- Restore the latest SQLite snapshot on startup when available.
- Upload refreshed SQLite snapshots after cache writes and at the end of sync cycles.
- Keep `DATABASE_URL` support only as a secondary backend path, not the primary recommendation.

## Why Google Drive snapshot storage

- The app mostly works like a durable file cache, not like a high-throughput transactional database.
- Hosted page renders should read from local SQLite, not from a remote database on every rerun.
- Uploading one SQLite snapshot occasionally is far cheaper than repeated remote query traffic.
- This avoids the free-tier network-transfer failure mode that appeared with Neon.

## Implementation steps

1. Introduce a storage factory that prefers Google Drive snapshot storage when Drive secrets are present.
2. Restore the SQLite file from Drive before opening the local match store.
3. Attach snapshot upload hooks to SQLite commits and explicit end-of-cycle flushes.
4. Keep the existing match-store contract so service/UI code continues reading from local SQLite.
5. Retain SQLite-only mode for local dev/test stability.
6. Keep `DATABASE_URL` as a fallback/secondary path without making it the default recommendation.
7. Add regression coverage for backend selection and snapshot-hook wiring.

## Remaining operational step

- Add `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DRIVE_FOLDER_ID` to Streamlit app secrets.
- After that, reboot/redeploy should no longer wipe the critical cache because the app can restore the last uploaded SQLite snapshot.
