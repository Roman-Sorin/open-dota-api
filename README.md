# OpenDota Turbo Dashboard + CLI

This project now contains:

- Turbo-focused web dashboard (Dotabuff-like experience) for personal stats
- Existing CLI for quick terminal queries

## Main app: Turbo Dashboard (recommended)

Turbo-only dashboard for your account:

- Flexible time filter:
  - period in days, or
  - multi-select patches (e.g. `7.40`, `7.40c`, `7.39b`)
  - explicit `Start Date` mode
  - default mode is `Patches`, preselected to patch family `7.41` (`7.41` plus any available `7.41x` letter patches)
  - default baseline/start is `2026-03-24`
- Hero overview in Turbo (matches, won matches, lost matches, WR, avg K/D/A, avg duration, avg net worth, avg damage, KDA, max kills, max hero damage)
- Hero overview highlights won matches in green and lost matches in red
- Hero Overview column labels stay short and English-only: `All`, `Won`, `Lost`, `WR`, `Dur`, `NW`, `Dmg`
- All winrates in the UI use the same colors: below `50%` red, exactly `50%` yellow, above `50%` green
- Hero overview and detailed hero stats now share one metric-definition source in the UI, so added hero fields stay aligned in both places
- Hero overview aggregation now also comes from one shared service-side stats source, so values like `Rad WR` and `Dire WR` stay identical between overview and detailed hero stats
- Dashboard dataframe styling now uses a pandas compatibility helper that prefers `Styler.map` and falls back to `applymap`, preventing cloud/runtime pandas changes from crashing Hero Overview or Item Winrates
- When Turbo match rows miss `hero_damage` or `net_worth`, the app enriches overview/detail stats from match details stored locally
- Cached Hero Overview now also enriches missing `hero_damage` and `net_worth` from stored match details, so heroes do not stay stuck at zero when the local summary rows were incomplete
- Hero Overview is now built from a validated snapshot that tracks match-detail coverage; incomplete zero-value snapshots are rejected instead of being rendered as valid analytics
- Reported bad matches `8743652071` and `8745970611` are excluded centrally from all dashboard statistics and hero sections
- Top dashboard metrics include Turbo matches, wins, losses, and winrate; Turbo wins are green and Turbo losses are red
- Separate multipage `Database` view monitors Turbo cache coverage for the selected player over a rolling window (default `365` days)
- `Database` shows match-level cache status (`detail cached`, `timings ready`, `parse pending`) plus cycle history, cooldown state, and contiguous full-coverage range
- `Database` can run one bounded background-cache cycle per refresh and optionally auto-run while that page stays open
- `Database` auto-fill now refreshes only the live sync section instead of reloading the whole page on each cycle
- `Database` auto-fill is now driven by a tiny `st.fragment(run_every=...)` timer that requests a full app rerun, and the next full page pass performs the sync cycle
- `Database` `Sync History` now includes a `Source` column so you can see whether each run was `Manual`, `Auto`, or `Forced`
- `Database` summary sync now still inspects the newest OpenDota page during long-window cooldowns, so fresh matches show up without waiting for the old 12-hour incremental throttle to expire
- `Database` background cycles now keep a separate summary head-sync cooldown, so auto-fill can keep working from cached matches/STRATZ without hammering OpenDota summaries on every 15-second rerun
- `Database` also keeps a separate STRATZ retry window, so a temporary STRATZ `429` no longer causes the app to silently hammer the Stats fallback on every subsequent cycle
- `Database` background auto-fill now avoids mixing OpenDota and STRATZ work in the same cycle, so one provider's rate limit does not immediately cascade into a second provider attempt with no user-visible progress
- Parse-only retry cycles no longer start the pending-parse quiet window, so the queue can poll freshly retried jobs on the next cycle instead of self-blocking behind repeated `Waiting...` notes
- Default `Database` `Balanced` mode now uses `5` detail fetches, `5` parse requests, and a `15` second interval
- `Cached Matches` now supports pagination with configurable page size and direct navigation to first/previous/next/last pages
- `Database` times are shown in Israel time and the page now exposes user-facing `Sync Speed` presets (`Safe`, `Balanced`, `Fast`) instead of only raw batch knobs
- Default selected hero is `Spectre` when that hero exists in the current overview snapshot; otherwise the first available hero is used
- Dashboard loading is manual by section:
  - cached overview data can auto-open from local SQLite storage when available
  - `Refresh Turbo Dashboard` and the dedicated `Database` page are the only UI flows allowed to talk to OpenDota for cache sync/detail hydration
  - `Refresh Hero Details`, `Refresh Item Winrates`, and `Refresh Recent Matches` rebuild from the currently loaded dashboard snapshot for the selected hero
- Section refreshes no longer pull newer matches than the currently loaded overview; only `Refresh Turbo Dashboard` advances the dataset
- `Refresh Turbo Dashboard` is now cache-first: it rebuilds the dashboard from the local match cache and only performs one bounded OpenDota head-sync to check for newer matches
- If that bounded OpenDota head-sync is rate-limited or temporarily unavailable, the dashboard keeps rendering the cached snapshot instead of failing the whole page
- Dashboard refresh no longer requires a fresh OpenDota player-profile lookup when the selected player's Turbo cache already exists locally
- If the current cached snapshot still lacks required match details for some heroes, the app does not render that overview as valid data and tells you to rebuild the snapshot
- Detailed hero section in Turbo includes avg duration, avg damage, avg net worth, max kills, and max hero damage
- Selected-hero section refreshes are grouped into one action bar above the sections (`Hero Details`, `Matchups`, `Item Winrates`, `Recent Matches`)
- Selected-hero sections now open automatically for the current hero snapshot; `Refresh All Hero Sections` rebuilds them, but you no longer need it just to reveal them
- Selected-hero sections restore independently from cache across reruns; refreshing one section must not hide another already loaded section for the same hero snapshot
- The action bar also includes `Refresh All Hero Sections` so all four selected-hero sections can be rebuilt in one Streamlit rerun
- Matchups section now uses the same two-table layout everywhere: `Teammates` and `Opponents`
  - Both `Selected Hero` and `All Heroes` show the same column order: `Hero Icon / Hero / WR / Matches / Won / Lost`
  - In Matchups, only `WR` is color-coded; `Won` and `Lost` stay neutral
  - In `All Heroes`, `Player Teammates` default to highest `WR` first, while `Player Opponents` default to lowest `WR` first
  - Matchup winrates remain numeric under the hood so both built-in sorting and user-click sorting treat `100.00` correctly
  - Changing `Min matchup matches` only filters the already built matchup snapshot; it does not require pressing `Refresh Matchups` again
  - `Refresh Matchups` is cache-only for match details and does not call OpenDota for missing details
  - If no cached player-composition details exist for the current snapshot yet, Matchups now says so explicitly and points you to `Refresh Turbo Dashboard`
  - Matchup tables now keep the current built snapshot across Streamlit reruns, so changing `Min matchup matches` does not discard already built rows
- `Refresh Hero Details`, `Refresh Matchups`, `Refresh Item Winrates`, and `Refresh Recent Matches` are all cache-only section rebuilds; they never fetch uncached match details from OpenDota
- Experimental Hero Trends stays at the bottom and currently shows daily trends for the selected hero
- Hero detail, item stats, and recent matches stay cached per hero/filter in the current session when you switch between heroes
- Detail-section caches are scoped to the current dashboard snapshot so old hero/recent/item rows are not reused after the overview changes
- Section caches are invalidated only by real dashboard sync timestamps; local enrichment writes do not count as a new snapshot and must not close already built sections
- Section actions are refresh actions now; if dashboard data is newer than a section cache, the UI shows a stale hint instead of silently hiding that fact
- Hero Overview snapshots with suspicious per-hero zero `NW`/`Dmg`/`Max Dmg` rows are auto-invalidated and rebuilt instead of being rendered as valid data
- Item winrates count only end-of-match inventory items; cached match details add backpack slots, and summary-only fallback uses final slot columns only
- Item winrates use a dedicated section-schema cache key so legacy session payloads from the old purchase-log behavior are not reused after updates
- Item winrates also self-rebuild from cached final inventory/backpack data when a mixed-runtime session still exposes a legacy purchase-based snapshot after deploy
- Item winrates include average timing as a small badge on the item icon, sourced from cached timing data for matches where the item remains in the final inventory/backpack snapshot
- Item timing chips are rounded to whole minutes and item icons keep their original aspect ratio instead of being forced into square thumbnails
- `Item Winrates` now reuses the same table shell styling as `Recent Matches`, so borders, header rhythm, and row dividers stay visually aligned
- `Item Winrates` is rendered through the same Streamlit markdown-table path as `Recent Matches`, avoiding wrapper-level style drift between `stHtml` and markdown containers
- `Item Winrates` header cells are sortable again via click without dropping item icon chips, timings, or buff badges
- Clicking the `Item` header in `Item Winrates` now sorts by average item timing rather than alphabetically
- Item winrates also include end-of-match consumable buffs (`Aghanim's Scepter`, `Aghanim's Shard`, `Moon Shard`) when cached details expose them, and those rows are marked with a small `buff` chip on the item icon
- Item winrates now show a coverage warning when cached match details are missing, instead of silently presenting partial counts as complete analytics
- Item winrates table shows `Matches`, `Won`, and `Lost`; `Won` is green and `Lost` is red
- Item winrates UI has a safe legacy fallback, so mixed deploy/runtime restarts do not crash if an older service object is still alive during a rerun
- Item winrates no longer show Avg K/D/A or derived KDA columns
- Recent hero matches shown as a compact one-row-per-match table under the item table
- Recent hero matches show only final slots, and item timings are shown only when the final item completion time is available
- Recent hero matches also show consumable buffs from cached match details and mark them with a small `buff` chip
- When final-item timings are available, recent-match items are ordered by earliest completion time
- Recent hero matches include `Net Worth` and player `Hero Damage`
- Recent hero matches show both `K/D/A` and per-match `KDA` rounded to one decimal
- Recent hero matches support `Load 10 more matches`
- Item winrates are ordered by highest winrate first (then by match count)
- Default minimum matches per item in the dashboard filter is `1`
- Dashboard clears stale overview session data when schema changes between app updates

Live app:
- https://open-dota-api-kzxvl2fznpz4cwwpfk2jmp.streamlit.app/

### Run

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate

pip install -r requirements.txt
streamlit run webapp/turbo_dashboard.py
```

Then open the local URL printed by Streamlit (usually `http://localhost:8501`).

## Optional API key

OpenDota key is optional.

```bash
copy .env.example .env
```

Set keys only if needed:

```env
OPENDOTA_API_KEY=
STRATZ_API_TOKEN=
DATABASE_URL=
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON=
GOOGLE_DRIVE_FOLDER_ID=
GOOGLE_DRIVE_SNAPSHOT_NAME=matches.sqlite3
GOOGLE_DRIVE_MIN_UPLOAD_INTERVAL_SECONDS=60
```

Recommended production persistence is Google Drive snapshot storage. When `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DRIVE_FOLDER_ID` are configured, the app restores `.cache/matches.sqlite3` from Google Drive at startup and uploads the updated snapshot back after sync/write activity. This keeps the hosted Streamlit app on fast local SQLite while still surviving reboot/redeploy. `DATABASE_URL` remains optional as a secondary backend path. If external persistence is configured but invalid, the app now shows a visible warning and falls back to local SQLite instead of crashing blindly.

## CLI (still available)

```bash
python main.py stats --player 1233793238 --hero "Chaos Knight" --mode turbo --days 60
python main.py items --player 1233793238 --hero ck --mode turbo --days 60
python main.py matches --player 1233793238 --hero ck --mode turbo --days 60 --limit 20
python main.py ask "дай мне статистику по игроку 1233793238 на Chaos Knight в турбо за последние 2 месяца"
```

## Architecture

```text
main.py
cli/
  app.py
  commands.py
webapp/
  turbo_dashboard.py
services/
  analytics_service.py
clients/
  opendota_client.py
parsers/
  input_parser.py
formatters/
  output_formatter.py
models/
  dtos.py
utils/
  cache.py
  config.py
  exceptions.py
  helpers.py
tests/
  test_parsers.py
  test_helpers.py
```

## OpenDota limitations

- Some `players/{id}/matches` rows may have empty `item_0..item_5` (especially Turbo cases).
- Missing detail-heavy fields are hydrated during the main dashboard refresh and then reused from local storage by all sections.
- Main dashboard refresh now also attempts OpenDota parse-based backfill for missing item timings on cached final-inventory matches, so newly synced matches usually do not require pressing the manual repair button.
- Player matches are persisted in local `SQLite` storage and reused for later filters/analytics.
- Match details are persisted separately and reused for enrichment-heavy sections.
- The service performs incremental syncs instead of refetching whole history on each reload.
- Background worker metadata is also persisted in local `SQLite` so the `Database` page can show cache progress and recent sync-cycle history.
- For Streamlit Cloud durability, the recommended setup is Google Drive snapshot storage via `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` + `GOOGLE_DRIVE_FOLDER_ID`. The app restores the SQLite file from Drive on startup and uploads fresh snapshots after cache writes, so normal page reads stay local and cheap.
- `DATABASE_URL` is still supported as a secondary backend path, but a live remote database is no longer the recommended default for this app's cache pattern.
- `purchase_log` is often incomplete; the dashboard uses it for recent-match timing repair only, not for `Item Winrates`.
- If `STRATZ_API_TOKEN` is configured, cached matches that still miss item timings after OpenDota detail fetches can now recover those timings from STRATZ match purchase events.
- STRATZ fallback does not replace OpenDota for summaries/details; it only fills missing timing fields (`purchase_log` / `first_purchase_time`) when OpenDota leaves them empty.
- If STRATZ successfully fills timings for a match that had an outstanding OpenDota parse request, the app now completes that pending parse row so `Pending Parse` reflects only matches still blocked on external timing data.
- The background sync cycle now stops enqueueing new OpenDota parse jobs while an older pending parse backlog still exists, so the queue is drained before it is expanded further.
- If an older parse backlog stays stuck, the sync cycle now re-requests a bounded batch of stale pending parses so the app does not sit on `150 pending` forever without submitting anything new.
- `Database` `Sync History` notes now say whether the cycle was waiting on active parse jobs or retrying stale ones.
- Recently retried pending parses are now rechecked before the rest of the older backlog, so `Pending Parse` drops as soon as OpenDota finishes those jobs instead of staying flat for many cycles.
- Fresh pending parses are no longer re-polled from OpenDota on every 15-second auto cycle. The app now waits before polling, prefers cached/STRATZ timing recovery first, and only then rechecks OpenDota so the background page does not create self-inflicted rate limits.
- Pending parse requests now store the OpenDota `jobId` and poll the lighter `request/{jobId}` status path before fetching `matches/{id}` again. This keeps the background queue aligned with OpenDota's async parse flow and cuts down needless detail polling.
- STRATZ timing fallback now targets the actual `pending` / missing-timing backlog first instead of only walking the newest cached matches. Older unresolved matches are no longer starved just because recent rows already have ready timings.
- After a sync cycle already performed OpenDota work, the next pending-parse check now waits through a short quiet period instead of immediately polling again. This reduces self-inflicted `429` responses on the auto-refreshing `Database` page.
- Passive `waiting on pending parse jobs` cycles no longer refresh `last_polled_at` for those rows. This keeps the stale-retry timer moving forward so old `pending` jobs can be retried instead of being stuck in an endless wait loop.
- Recent match item chips now mark `Moon Shard`, `Aghanim's Scepter`, and `Aghanim's Shard` as `buff` only when match details explicitly report them as permanent buffs/consumed upgrades. A plain inventory item is no longer mislabeled as a buff just because `first_purchase_time` exists.
- `match_parse_requests` rows now persist `request_source` and `request_reason` so pending-queue diagnostics can distinguish new OpenDota requests, stale retries, STRATZ-based completions, and other queue transitions.
- Stale pending retries are now anchored to the last parse request time (`requested_at`), not to the most recent poll timestamp. Recently checked rows that are still stale no longer get trapped in the `waiting` bucket just because a status check touched them.
- `Sync History` runs now persist and display both `Requested Via` and `Data From`, so each cycle can show which provider was queried (`OpenDota` / `STRATZ`) and which provider actually supplied recovered data.
- `Database` metrics now break `Pending Parse` into actionable buckets: `Pending Waiting`, `Pending Poll Due`, `Pending Retry Due`, `Pending Legacy`, and `Pending Ready-Stuck`. This is a diagnostics-only change that makes a stuck `150 pending` backlog explainable without reading raw queue rows.
- Pending-refresh no longer issues hidden STRATZ timing-recovery requests per queued replay-parse row. STRATZ recovery now stays in its own bounded stage so the app does not create a second provider rate-limit loop while polling the OpenDota parse queue.
- Waiting pending rows no longer mark the cycle as `Requested Via: OpenDota` unless the cycle actually polled or retried OpenDota parse jobs. This keeps `Sync History` honest and allows STRATZ fallback to run on truly cache-only / no-op pending cycles.
- Bounded STRATZ timing recovery can now run after successful OpenDota pending-queue work, as long as the cycle is not currently OpenDota-rate-limited. The provider columns stay honest because `Requested Via: STRATZ` is now stamped only when a real STRATZ network attempt happened.
- Provider backoff is now asymmetric on the `Database` page: a pending-parse OpenDota `429` stretches the next pending poll window to several minutes, and a STRATZ `429` stretches the next STRATZ retry window to roughly fifteen minutes. This prevents the page from self-spamming both providers every minute after one bad cycle.
- Temporary OpenDota upstream outages like HTTP `522` are now retried once and then folded into the same cooldown-style handling as other transient OpenDota availability problems, instead of surfacing as a hard sync error immediately.
- Streamlit Community Cloud does not provide a true always-on worker inside the page process. The `Database` page can keep advancing the backlog while it stays open, but a real 24/7 worker still requires an external runner with shared persistent storage.

## Timing backfill job

For already cached matches, you can backfill missing parsed item timings without opening the UI:

```bash
python scripts/backfill_item_timings.py --player 1233793238 --patch 7.41 --patch 7.41a --batch-size 100
```
- Without API key, rate limits can be hit.

## Autonomous cache worker

If you want the cache job to run without pressing buttons in the UI, run the standalone worker:

```bash
python scripts/background_sync_worker.py --player 1233793238 --window-days 365 --interval-seconds 60 --pause-after-429-seconds 600
```

- This worker runs outside Streamlit UI.
- It keeps looping on its own:
  - sync summaries
  - fetch missing match details
  - submit replay parses
  - sleep normally between cycles
  - pause longer after `HTTP 429`
- `--once` runs a single cycle and exits.

## Dependency policy

- Runtime and test dependencies in [requirements.txt](/C:/development/projects/open-dota-api/requirements.txt) are pinned to exact versions.
- Purpose: keep Streamlit Cloud restarts and local rebuilds on the same package set, instead of silently upgrading to newer pandas/Streamlit combinations.
- Upgrade dependencies intentionally, verify the app, then commit the new pins in the same change.

## Tests

```bash
pytest -q
```

## Collaboration Rules

- After completing any implementation change, update relevant Markdown docs (`README.md`, `APP_GUIDE.md`, etc.) when behavior, UX, setup, or workflows changed.
- Follow the repository self-check checklist in [SELF_CHECK_WORKFLOW.md](/C:/development/projects/open-dota-api/SELF_CHECK_WORKFLOW.md) for validation, regression coverage, deploy verification, and documentation hygiene after every change.
- After changes are complete and validated, commit and push to the remote branch in the same working session.
