# Turbo Buff App Guide

## What this app is

Turbo Buff is a Python application for analyzing your Dota 2 **Turbo-only** statistics via OpenDota.

The project includes two interfaces:

- **Web dashboard (recommended)**: Dotabuff-like personal analytics UI
- **CLI**: terminal commands for stats/items/matches and free-text query mode

## Main capabilities

- Turbo-only hero overview (matches, won matches, lost matches, winrate, avg duration, avg net worth, avg damage, max kills, max hero damage)
- Hero Overview shows won matches in green and lost matches in red
- Hero Overview column labels stay short and English-only: `All`, `Won`, `Lost`, `WR`, `Dur`, `NW`, `Dmg`
- Hero Overview and Detailed Turbo Stats use one shared metric-definition list in UI code, so hero fields stay synchronized between both sections
- Hero Overview and Detailed Turbo Stats also share manual match-tag metrics: `MVP`, `High`, and combined `Tag` / `Tagged Matches`
- The top dashboard summary cards also show overall `MVP`, `Highlighted`, and `Tag` totals formatted as `count (pct%)`
- Those tag metrics are rendered as `count (pct%)`, where the percent is the rounded share of the hero's total matches
- Hero Overview rows are also built from the same service-side stats aggregation used by Detailed Turbo Stats, so `Radiant WR` / `Dire WR` and other hero metrics stay consistent
- Dashboard table styling uses a pandas-compatibility helper (`Styler.map` with `applymap` fallback) so cloud/runtime package drift does not break Hero Overview or Item Winrates rendering
- All winrate values in the UI use the same colors: below `50%` red, exactly `50%` yellow, above `50%` green
- Hero overview avg damage/net worth use match-detail fallback when player match rows don't include `hero_damage` or `net_worth`
- Cached Hero Overview also reuses stored match details to backfill missing hero economy/damage fields before rendering overview rows
- Hero Overview is now built from a validated snapshot that tracks match-detail coverage; incomplete zero-value snapshots are rejected instead of being rendered as valid analytics
- Reported bad matches `8743652071` and `8745970611` are excluded centrally from all statistics and selected-hero sections
- Dashboard summary cards: Turbo matches, wins, losses, winrate; Turbo wins are green and Turbo losses are red
- Separate multipage `Database` view tracks cache coverage for one player's Turbo matches over a rolling window (default `365` days)
- `Database` shows match-level cache states, replay-parse backlog, recent sync-cycle history, cooldown state after 429s, and the contiguous date range that is already fully cached
- `Database` can run one bounded cache-fill cycle per refresh and optionally auto-run while that page remains open
- `Database` auto-fill now uses browser-bound page reruns for reliability on Streamlit Cloud, so the data section is always rendered even when fragment rendering is unstable
- `Database` auto-fill is now driven by a tiny `st.fragment(run_every=...)` timer that requests a full app rerun; the next full page pass performs one sync cycle
- `Database` `Sync History` now includes a `Source` column so you can distinguish `Manual`, `Auto`, and `Forced` runs
- `Database` summary sync now still checks the newest OpenDota page during long-window incremental cooldowns, so newly played matches appear promptly instead of waiting up to 12 hours on a `365`-day window
- `Database` now keeps a separate summary head-sync cooldown, so auto-fill can keep maintaining cached matches and STRATZ timing recovery without re-hitting the OpenDota summaries endpoint every cycle
- Those background head-sync checks no longer advance the dashboard `last_incremental_sync_at`; the main dashboard snapshot timestamp changes only on real dashboard syncs
- `Database` now also keeps a separate STRATZ retry window, so a temporary STRATZ `429` no longer triggers hidden repeated Stats retries on every auto-fill cycle
- `Database` auto-fill now avoids mixing OpenDota and STRATZ work in one cycle, so a rate limit from one provider does not immediately trigger a second provider attempt in that same run
- Parse-only retry cycles no longer start the pending-parse quiet window, so freshly retried replay parses can be checked on the very next cycle instead of getting stuck behind repeated `Waiting...` messages
- Default `Database` `Balanced` mode now uses `5` detail fetches, `5` parse requests, and a `15` second interval
- Default `Database` cooldown after `HTTP 429` is now `50` seconds
- `Cached Matches` now has real pagination: page size, page number, and `First/Prev/Next/Last` navigation
- `Database` times are rendered in Israel time
- `Database` exposes `Sync Speed` presets (`Safe`, `Balanced`, `Fast`) for normal use; raw detail/parse batch controls remain under `Advanced settings`
- `Database` Postgres/Neon reads now run in autocommit mode so fresh sync runs and newly cached matches appear immediately instead of sticking to an older transaction snapshot inside a long-lived Streamlit session
- Time filter modes: `Days`, `Patches`, `Start Date`
- Default time filter mode is `Patches`, preselected to patch family `7.41` (`7.41` plus any available `7.41x` letter patches)
- Default baseline/start date is `2026-03-24`
- Dashboard sections load manually and independently to reduce one-shot API work on page open
- Default selected hero in the hero dropdown is `Spectre` when present in the loaded overview; otherwise the first available hero is used
- If matching dashboard data already exists in local SQLite storage, the app restores Hero Overview automatically on page load for the current filters
- `Refresh Turbo Dashboard` is cache-first: it rebuilds the hero overview from the local cache and then does one bounded OpenDota head-sync only to check whether newer matches exist
- `Refresh Turbo Dashboard` and the dedicated `Database` page are the only UI actions that may talk to OpenDota
- If that bounded OpenDota check is rate-limited or temporarily unavailable, the dashboard keeps showing the cached snapshot and warns instead of failing the whole page
- Service startup also falls back to a checked-in compact OpenDota reference snapshot for heroes, items, and patches when live constants are temporarily unavailable, so Streamlit Cloud cold starts still render
- Mixed-runtime Streamlit reloads now still recognize temporary OpenDota exceptions during refresh, so cached-dashboard fallback remains active instead of showing a generic `Unexpected error`
- If the player's Turbo cache already exists locally, dashboard refresh no longer requires a separate OpenDota player-profile lookup before rebuilding the view
- If the current cached snapshot still lacks required match details for some heroes, the app does not render that overview as valid data and tells you to rebuild the snapshot
- `Refresh Hero Details`, `Refresh Item Winrates`, and `Refresh Recent Matches` rebuild the selected hero sections from the currently loaded dashboard snapshot
- Selected-hero refresh actions are grouped into one shared action bar above the detail sections, including `Refresh Matchups`
- Selected-hero sections restore independently from cache across reruns; refreshing one section must not hide another already loaded section for the same hero snapshot
- The action bar also includes `Refresh All Hero Sections` so all four selected-hero sections can be rebuilt in one Streamlit rerun
- `Refresh Hero Details`, `Refresh Matchups`, `Refresh Item Winrates`, and `Refresh Recent Matches` are cache-only section rebuilds and do not issue hidden OpenDota detail fetches
- Selected-hero sections (`Hero Details`, `Matchups`, `Item Winrates`, `Recent Matches`) now open automatically for the current hero snapshot; `Refresh All Hero Sections` remains a manual rebuild action, not the only way to reveal them
- Per-hero detailed stats (avg K/D/A, KDA, avg duration, avg net worth, avg damage, max kills, max hero damage, Radiant/Dire WR)
- Matchups section now uses the same two-table layout everywhere: `Teammates` and `Opponents`
  - Both `Selected Hero` and `All Heroes` use `Hero Icon / Hero / WR / Matches / Won / Lost`
  - Matchup tables intentionally omit `Avg K/D/A` and `KDA`
  - In Matchups, only `WR` uses semantic color; `Won` and `Lost` stay neutral
  - In `All Heroes`, `Player Teammates` default to highest `WR` first and `Player Opponents` default to lowest `WR` first
  - Matchup `WR` stays numeric in the dataframe; percent formatting is applied only at render time so sorting remains correct
  - Adjusting `Min matchup matches` filters the cached matchup rows and does not require a second `Refresh Matchups`
  - `Min matchup matches` defaults to `4`
  - `Refresh Matchups` uses cached match details only; it will not spend API calls to hydrate missing details
  - If the current snapshot does not yet have cached player-composition detail payloads, Matchups now shows an explicit hint to run `Refresh Turbo Dashboard`
  - Matchup tables keep the current built snapshot across Streamlit reruns, so changing `Min matchup matches` does not discard already built rows
- Experimental Hero Trends stays at the bottom and currently shows daily trend charts for the selected hero
- When you switch away from a hero and return, already loaded hero details/item stats/recent matches are restored from session cache for that hero/filter combination
- Detail-section caches are tied to the current dashboard snapshot, so a newer overview will not silently reuse old hero/item/recent rows
- Recent match rows use a dedicated section-schema cache key for the manual-tag row shape, so pre-tag session payloads are not reused after deploy
- Section caches are invalidated only by real dashboard sync timestamps; local enrichment writes do not count as a new snapshot and must not close already built sections
- Cached day-based hero snapshots are anchored to the newest cached match in that snapshot, so a stale cached overview does not silently lose rows just because wall-clock time advanced between reruns
- Cache-only selected-hero rebuilds now batch cached match-detail reads per section, so `Recent Matches`, item snapshots, hydration scans, and STRATZ timing recovery avoid per-match SQLite lookups on every rerun
- If the dashboard was refreshed later than a section, the section shows a hint that it should be rebuilt from the current dashboard snapshot with `Refresh ...`
- Overview snapshots with suspicious per-hero zero `NW`/`Dmg`/`Max Dmg` rows are treated as stale and rebuilt automatically
- Most frequent final items
- Item winrate table (wins with item / matches with item), includes per-item match count
- Item winrates count only end-of-match inventory items; cached match details add backpack slots, and summary-only fallback uses final slot columns only
- Item winrates use a dedicated section-schema cache key so older session payloads built from legacy purchase-log logic are not reused after deploys
- Item winrates self-rebuild from cached final inventory/backpack data in the UI if a mixed-runtime session still surfaces a legacy purchase-based snapshot after deploy
- Item winrates show average timing as a small badge on the item icon, using cached item timing data (`purchase_log` / `first_purchase_time` / Aegis objective time when available) for matches where the item is part of the end-of-match inventory snapshot
- Item timing chips round to whole minutes, and item thumbnails preserve the original Dota item aspect ratio instead of being forced into square boxes
- `Item Winrates` reuses the same table shell styling as `Recent Matches`, keeping borders, row dividers, and spacing consistent across both sections
- `Item Winrates` now renders through the same Streamlit markdown container path as `Recent Matches`, so wrapper-level border/padding differences from `stHtml` no longer apply
- `Item Winrates` column headers are clickable again for client-side sorting while preserving item icon chips, timings, and buff badges
- In `Item Winrates`, the `Item` header sorts by average item timing instead of alphabetic item name order
- Item winrates also include end-of-match consumable buffs (`Aghanim's Scepter`, `Aghanim's Shard`, `Moon Shard`) when cached match details expose them; buff entries are marked with a small `buff` chip on the item icon and use the same icon timing treatment as recent-match items
- Item winrates show an explicit coverage warning when some matches still lack cached item detail data, instead of silently undercounting them as if the snapshot were complete
- Main dashboard refresh rehydrates legacy cached match-detail rows that are missing the selected-player `purchase_log`, so recent-match item timings can recover without manual cache deletion
- Main dashboard refresh also attempts parse-based timing backfill for cached final-inventory matches that still have `version = None`, reducing the need to press the manual repair button for newly synced matches
- Item winrate table shows `Matches`, `Won`, and `Lost`; `Won` is green and `Lost` is red
- Item winrates section has a safe legacy fallback path so mixed deploy/runtime restarts do not crash the section if the process still holds an older service object
- Item winrate table no longer shows Avg K/D/A or derived KDA columns
- Item winrate table is sorted by highest item winrate first (ties by larger sample)
- Dashboard filter `Min matches per hero` defaults to `4`
- Dashboard filter `Min matches per item` defaults to `4`
- Recent hero matches are displayed as a compact table below the item table
- Recent hero matches show saved manual match tags inline and include an in-table native `Edit Tags` button on each visible match row
- Manual match tags are persisted as separate user data in the match store, not embedded into OpenDota summary/detail payloads
- Recent hero matches show final item slots only; timings are attached only to those final items when available from match details
- Recent hero matches also show consumable buffs from cached match details (for example consumed `Aghanim's Scepter`), marked with a small `buff` chip and ordered alongside timed final items
- In `Recent Matches`, regular end-of-match items stay left-aligned within the `Items` cell while consumable buffs are grouped against the right edge of that same cell
- Recent hero matches repair legacy cached item timings on the next main dashboard refresh when an older stored detail row is missing `purchase_log`
- If `Recent Matches` is already visible, `Refresh Turbo Dashboard` rebuilds that section from cached data in the same rerun so repaired item timings appear immediately
- `Refresh Turbo Dashboard` now persists the whole active snapshot in one pass: OpenDota summary sync, cached match-detail hydration, and item-timing backfill/parse submission all run during the main refresh instead of requiring hero-by-hero manual repair
- `Repair Missing Item Timings via OpenDota Parse` explicitly requests OpenDota replay parses for the visible recent hero matches that still have no timing data, waits briefly, then rebuilds the section from the refreshed cached details
- When final-item timings are available, recent-match items are ordered by earliest completion time
- Recent hero matches include `Net Worth` and player `Hero Damage`
- Recent hero matches show both `K/D/A` and per-match `KDA` rounded to one decimal
- Recent hero matches support incremental loading via `Load 10 more matches`
- The `Recent Matches` table uses content height so the `Load 10 more matches` control sits immediately below the visible rows instead of at the bottom of an oversized wrapper
- Supports player input as account id or OpenDota profile URL
- Local `SQLite` storage for player match summaries
- Separate persisted storage for fetched match details
- Separate persisted storage for background sync state, sync-cycle history, and replay-parse request tracking
- Optional Google Drive snapshot persistence for the critical match cache so cached matches/details survive app restarts and redeploys while the app still reads from local SQLite
- Optional Postgres-backed durable store remains supported as a secondary backend path
- Incremental summary sync to avoid repeated full-history calls
- Match details can be backfilled later without rebuilding summary history
- Graceful handling of missing OpenDota fields and rate limits
- Streamlit Community Cloud does not provide a real always-on worker in the app process. `Database` auto-run works only while that page stays open; a true 24/7 worker still needs an external runner plus shared storage.

## Project entry points

- Web dashboard: `webapp/turbo_dashboard.py`
- CLI entry: `main.py`

## Requirements

- Python 3.12+
- Internet access
- Dependencies are pinned exactly in [requirements.txt](/C:/development/projects/open-dota-api/requirements.txt) so deployed Streamlit environments do not drift across restarts

## Setup

```powershell
cd C:\development\projects\open-dota-api
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Optional environment file:

```powershell
copy .env.example .env
```

`OPENDOTA_API_KEY` is optional. Without a key, rate limits may be hit more often.
`STRATZ_API_TOKEN` is also optional and only needed for timing fallback when OpenDota lacks item timings for a match.
Recommended production persistence is Google Drive snapshot storage. Configure `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` and `GOOGLE_DRIVE_FOLDER_ID` so the app can restore `.cache/matches.sqlite3` from Drive at startup and upload fresh snapshots after cache writes. `DATABASE_URL` remains optional as a secondary backend path. If external persistence is invalid or unreachable, the UI shows an explicit warning and the app falls back to local SQLite.

## Run the web dashboard (recommended)

```powershell
streamlit run webapp/turbo_dashboard.py
```

Then open:

- `http://localhost:8501`

## Run CLI

```powershell
python main.py stats --player 1233793238 --hero "Chaos Knight" --mode turbo --days 60
python main.py items --player 1233793238 --hero ck --mode turbo --days 60
python main.py matches --player 1233793238 --hero ck --mode turbo --days 60 --limit 20
python main.py ask "show my winrate and kda on chaos knight 1233793238"
```

## Notes on OpenDota data

- Some Turbo rows from `players/{id}/matches` can have empty item slots.
- Match-detail-heavy fields are hydrated during the main dashboard refresh and then reused from local storage by all sections.
- Some requested metrics may depend on detail payload fields that are not guaranteed in every parsed match. Lane-derived values are currently not shown in the UI until the data source is made reliable.
- `purchase_log` is often incomplete; the dashboard uses it for recent-match timing repair only, not for `Item Winrates`.
- If `STRATZ_API_TOKEN` is configured, the app can recover missing match item timings from STRATZ when OpenDota detail payloads have no `purchase_log` / `first_purchase_time`.
- STRATZ fallback is timing-only. Match summaries and main detail payloads still come from OpenDota.
- When STRATZ timing recovery succeeds for a match that was previously marked `Pending Parse`, the app now marks that pending OpenDota parse request as completed so the `Pending Parse` count can drop instead of staying artificially inflated.
- The background sync cycle now prioritizes resolving existing pending parse jobs before enqueueing new OpenDota parse requests, so `Pending Parse` no longer grows forever while old jobs are still outstanding.
- If old OpenDota parse jobs stay stuck for too long, the background sync cycle now re-submits a bounded batch of stale pending parses instead of logging another `0 requested / 150 pending` cycle forever.
- `Sync History` notes now distinguish between actively waiting on existing parse jobs and retrying stale ones, so backlog runs explain what the app actually did.
- Recently retried pending parse jobs are now checked first on later cycles, so completed OpenDota parses clear out of `Pending Parse` promptly instead of waiting behind the entire older backlog.
- Fresh pending parse jobs are no longer force-polled against OpenDota every auto-refresh cycle; the app now waits a short poll delay, uses cached/STRATZ timing fallback first, and only then rechecks OpenDota so the dashboard does not lock itself into repeated `429` responses.
- Pending OpenDota parse rows now persist the returned `jobId` and poll `request/{jobId}` before refreshing `matches/{id}`. This follows the async job flow more closely, reduces unnecessary detail calls, and avoids self-inflicted rate-limit loops on the `Database` page.
- STRATZ timing fallback now prioritizes cached matches that are actually `pending` / missing timings, even when those matches are far down the window and the newest rows are already `Ready`. This prevents old timing backlogs from being starved forever by the newest match ordering.
- After a cycle already spent OpenDota quota on summary sync, detail hydration, or parse requests, the app now enters a short quiet period before the next pending-parse check. This prevents the immediate follow-up auto cycle from hitting `429` just because the previous cycle already did real work.
- Passive `Waiting on ... existing replay parse job(s)` cycles no longer rewrite `last_polled_at` on those pending rows. That preserves the stale-retry timer so old parse jobs can age into a bounded retry instead of being kept forever in the waiting state.
- Recent Matches now show `Moon Shard`, `Aghanim's Scepter`, and `Aghanim's Shard` as `buff` only when the cached match details confirm a consumed/permanent-buff state. A normal inventory copy stays in the regular item list without a `buff` badge.
- Parse-request storage now records `request_source` and `request_reason` on `match_parse_requests` rows. This is the first diagnostics step for the stuck `Pending Parse` backlog because it makes each queue transition traceable by provider and reason.
- Pending retry eligibility is now based on the last parse-request submission time, not on the most recent status-check timestamp. This prevents stale jobs from being endlessly reclassified as `recently checked` and skipped for retry.
- Database `Sync History` now includes provider provenance columns: `Requested Via` and `Data From`. This makes it visible whether a cycle touched `OpenDota`, `STRATZ`, or both, and whether any recovered timing data actually came from `STRATZ`.
- Database backlog metrics now split `Pending Parse` into five local-cache buckets: `Pending Waiting`, `Pending Poll Due`, `Pending Retry Due`, `Pending Legacy`, and `Pending Ready-Stuck`. The page now computes these counts directly from cached summaries/details/parse rows so the stuck replay-parse backlog is diagnosable without issuing new network requests.
- Pending replay-parse refresh no longer does implicit STRATZ timing recovery per row. STRATZ recovery now runs only in its own bounded maintenance stage, which avoids creating a hidden second rate-limit loop while the app is polling or retrying the OpenDota parse queue.
- Waiting pending rows no longer stamp the cycle as `Requested Via: OpenDota` unless the cycle actually hit an OpenDota parse endpoint. This keeps provider provenance accurate and stops cache-only pending cycles from blocking later bounded STRATZ maintenance.
- The bounded STRATZ maintenance stage may now run after successful OpenDota pending-queue work if the cycle is not OpenDota-rate-limited. Provider provenance remains accurate because `Requested Via: STRATZ` is only recorded when the stage actually made a STRATZ network attempt.
- The `Database` scheduler now uses longer provider-specific retry windows after `429`s: pending OpenDota parse polling is held back for several minutes, and STRATZ timing recovery is held back for roughly fifteen minutes. This is intended to stop the repeating one-minute `OpenDota 429 -> STRATZ 429 -> repeat` loop while the backlog is stuck.
- STRATZ `401/403` responses are now treated as provider auth/config blocks, not as generic empty fallback misses. The real provider error is persisted into background sync state and rendered on the `Database` page so token/IP failures are visible without reading server logs.
- OpenDota transient upstream failures such as Cloudflare `522` are now retried once in the client and then treated like a temporary cooldown condition instead of a hard background-sync `error` state.
- Streamlit Community Cloud local files are not durable storage. If neither Google Drive snapshot storage nor `DATABASE_URL` is configured, the app warns in the UI because a reboot/redeploy can reset the local `.cache/matches.sqlite3` file.

## Batch timing repair

For already cached matches in a specific patch window, run:

```powershell
python scripts/backfill_item_timings.py --player 1233793238 --patch 7.41 --patch 7.41a --batch-size 100
```

## Autonomous cache worker

If you want the cache-fill job to run without pressing buttons in the web UI, use:

```powershell
python scripts/background_sync_worker.py --player 1233793238 --window-days 365 --interval-seconds 60 --pause-after-429-seconds 600
```

What it does:

- runs the same bounded sync cycle used by the `Database` page
- keeps looping without the Streamlit page being open
- sleeps between normal cycles
- if OpenDota returns `HTTP 429`, sleeps longer and retries later

Use `--once` if you want exactly one cycle and then exit.

## Troubleshooting

- `ModuleNotFoundError`: activate `.venv` and reinstall requirements.
- `OpenDotaRateLimitError`: wait and retry, reduce period, or use `OPENDOTA_API_KEY`.
- Missing timings on a match that already has timings on Dotabuff can happen because Dotabuff and OpenDota use different data pipelines. With `STRATZ_API_TOKEN`, the app now tries STRATZ before leaving those timings as missing.
- Empty/partial item data: this can happen due to OpenDota coverage limits; app will still show available data.
- After app updates, dashboard data schema is auto-refreshed; if values still look stale, click `Refresh Turbo Dashboard` again.
