# Persistent Storage Plan

## Goal

Prevent cached match data from disappearing after Streamlit Cloud reboot, redeploy, or reset.

## Root cause

- Critical cache data was stored only in local `.cache/matches.sqlite3`.
- Streamlit Community Cloud does not guarantee local filesystem persistence across app restarts.

## Chosen solution

- Use external Postgres via `DATABASE_URL`.
- Recommended provider: Neon free tier.
- Keep local SQLite only as fallback for local development and tests.

## Why Neon

- Free tier is enough for the current cache footprint.
- No card-first setup was required for this user flow.
- Integration is simple: one connection string secret instead of several bucket credentials.

## Implementation steps

1. Introduce a storage factory that chooses Postgres when `DATABASE_URL` is present.
2. Keep the same match-store contract so service/UI code does not need feature-specific rewrites.
3. Retain SQLite as local fallback for dev/test stability.
4. Remove the earlier S3-replica branch to avoid dual persistence paths in production docs and code.
5. Add regression coverage for backend selection and local fallback behavior.
6. Wire Streamlit Cloud to the external database via one secret.

## Remaining operational step

- Add `DATABASE_URL` to Streamlit app secrets.
- After that, reboot/redeploy should no longer wipe the critical cache.
