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
- Before uploading, compare the Drive generation and file size with the local working copy. If Drive was changed outside the app or is materially larger, block the upload rather than overwriting a recovery snapshot with stale local data.
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

## Recovery and overwrite safety

- A Drive version restored manually does not change an already running Streamlit worker's local SQLite file. Reboot the app after selecting the intended Drive version so its fresh runtime downloads that version.
- Do not press dashboard refresh before that reboot: a running worker can otherwise upload its stale local cache.
- The Database page surfaces a blocked upload when Drive was changed elsewhere or holds a materially larger snapshot. This is intentional fail-closed behavior; keep both files and explicitly choose the recovery source.
