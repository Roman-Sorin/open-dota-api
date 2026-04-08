# Background Database Plan

## Goal

Add a dedicated `Database` page that shows how far the local Turbo cache has progressed for one player and can advance the cache backlog safely in small batches.

## Product intent

- Target scope: one player, Turbo-only, rolling window such as the last `365` days.
- Primary unit of storage and progress is the match.
- Cache should be explicit:
  - match summary cached
  - match detail cached
  - item timings ready
  - parse pending
- User should be able to open one page and immediately see:
  - how many Turbo matches are in scope
  - how many already have full detail coverage
  - how many still miss item timings
  - how far back contiguous full coverage currently reaches
  - whether the worker is in cooldown after an OpenDota rate limit

## Architecture decision

The app now uses a separate background-cache pipeline on top of the existing SQLite match store.

- Existing tables remain the source of truth for:
  - `player_matches`
  - `match_details`
  - `sync_state`
- New persistent worker metadata is stored in SQLite:
  - `background_sync_state`
  - `background_sync_runs`
  - `match_parse_requests`

This keeps the dashboard cache model intact while making worker progress inspectable.

## Streamlit constraint

Important limitation:

- Streamlit Community Cloud does not provide a true always-on worker inside the page process.
- The implemented v1 behavior is cooperative:
  - the `Database` page can run one sync cycle per page refresh
  - optional auto-run keeps advancing the queue while that page stays open
- A real 24/7 worker still requires an external runner plus shared persistent storage.

## Implemented v1

- Separate `Database` page in Streamlit multipage navigation.
- Persistent coverage/job state and run history in SQLite.
- One safe sync cycle can:
  - incremental-sync Turbo summaries
  - fetch a bounded batch of missing match details
  - request OpenDota replay parses for cached detail rows that still miss timings
  - enter cooldown after a 429 instead of hammering the token
- Match-level database table shows:
  - match id
  - played time
  - hero
  - result
  - K/D/A
  - duration
  - detail cache status
  - timing status
  - summary/detail cache timestamps

## Current persistence model

- Critical cache state lives in `matches.sqlite3`.
- The app now supports a durable S3-compatible replica for that SQLite file:
  - on startup, download remote `matches.sqlite3` if configured
  - after each committed cache write, upload the latest file back to remote storage
- This is the minimum viable fix for Streamlit Cloud restarts because local `.cache` files alone are not durable.

## Still not implemented

- True headless always-on worker on Streamlit Cloud
- Full external relational database replacement for SQLite
- Exact quota telemetry from OpenDota response headers
- Per-match manual retry controls

## Next reasonable upgrades

1. Replace the SQLite replica approach with a first-class external database if multi-writer or higher durability guarantees become necessary.
2. Run `run_background_sync_cycle(...)` from an external scheduler/worker.
3. Add richer backlog prioritization:
   - newest-first vs oldest-first modes
   - patch-scoped backlog
   - manual priority hero queue
4. Add parse retry backoff per match if OpenDota parse stays pending for a long time.
