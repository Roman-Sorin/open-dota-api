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
- Hero Overview rows are also built from the same service-side stats aggregation used by Detailed Turbo Stats, so `Radiant WR` / `Dire WR` and other hero metrics stay consistent
- All winrate values in the UI use the same colors: below `50%` red, exactly `50%` yellow, above `50%` green
- Hero overview avg damage/net worth use match-detail fallback when player match rows don't include `hero_damage` or `net_worth`
- Cached Hero Overview also reuses stored match details to backfill missing hero economy/damage fields before rendering overview rows
- Hero Overview is now built from a validated snapshot that tracks match-detail coverage; incomplete zero-value snapshots are rejected instead of being rendered as valid analytics
- Dashboard summary cards: Turbo matches, wins, losses, winrate; Turbo wins are green and Turbo losses are red
- Time filter modes: `Days`, `Patches`, `Start Date`
- Default baseline/start date is `2026-01-21`
- Dashboard sections load manually and independently to reduce one-shot API work on page open
- If matching dashboard data already exists in local SQLite storage, the app restores Hero Overview automatically on page load for the current filters
- `Refresh Turbo Dashboard` fetches/syncs the hero overview from OpenDota when you want newer matches
- `Refresh Turbo Dashboard` is the only UI action that may talk to OpenDota; it performs an incremental new-match check and hydrates missing match details for the current snapshot exactly once
- If the current cached snapshot still lacks required match details for some heroes, the app does not render that overview as valid data and tells you to rebuild the snapshot
- `Refresh Hero Details`, `Refresh Item Winrates`, and `Refresh Recent Matches` rebuild the selected hero sections from the currently loaded dashboard snapshot
- Selected-hero refresh actions are grouped into one shared action bar above the detail sections, including `Refresh Matchups`
- Selected-hero sections restore independently from cache across reruns; refreshing one section must not hide another already loaded section for the same hero snapshot
- The action bar also includes `Refresh All Hero Sections` so all four selected-hero sections can be rebuilt in one Streamlit rerun
- `Refresh Hero Details`, `Refresh Matchups`, `Refresh Item Winrates`, and `Refresh Recent Matches` are cache-only section rebuilds and do not issue hidden OpenDota detail fetches
- Per-hero detailed stats (avg K/D/A, KDA, avg duration, avg net worth, avg damage, max kills, max hero damage, Radiant/Dire WR)
- Matchups section now uses the same two-table layout everywhere: `Teammates` and `Opponents`
  - Both `Selected Hero` and `All Heroes` use `Hero Icon / Hero / WR / Matches / Won / Lost`
  - Matchup tables intentionally omit `Avg K/D/A` and `KDA`
  - In Matchups, only `WR` uses semantic color; `Won` and `Lost` stay neutral
  - Matchup `WR` stays numeric in the dataframe; percent formatting is applied only at render time so sorting remains correct
  - Adjusting `Min matchup matches` filters the cached matchup rows and does not require a second `Refresh Matchups`
  - `Refresh Matchups` uses cached match details only; it will not spend API calls to hydrate missing details
  - If the current snapshot does not yet have cached player-composition detail payloads, Matchups now shows an explicit hint to run `Refresh Turbo Dashboard`
  - Matchup tables keep the current built snapshot across Streamlit reruns, so changing `Min matchup matches` does not discard already built rows
- Experimental Hero Trends stays at the bottom and currently shows daily trend charts for the selected hero
- When you switch away from a hero and return, already loaded hero details/item stats/recent matches are restored from session cache for that hero/filter combination
- Detail-section caches are tied to the current dashboard snapshot, so a newer overview will not silently reuse old hero/item/recent rows
- Section caches are invalidated only by real dashboard sync timestamps; local enrichment writes do not count as a new snapshot and must not close already built sections
- If the dashboard was refreshed later than a section, the section shows a hint that it should be rebuilt from the current dashboard snapshot with `Refresh ...`
- Overview snapshots with suspicious per-hero zero `NW`/`Dmg`/`Max Dmg` rows are treated as stale and rebuilt automatically
- Most frequent final items
- Item winrate table (wins with item / matches with item), includes per-item match count
- Item winrates count cached purchased items first; when cached `purchase_log` is missing, the app falls back to cached final inventory / summary final slots for that match
- Item winrates show an explicit coverage warning when some matches still lack cached item detail data, instead of silently undercounting them as if the snapshot were complete
- Item winrate table shows `Matches`, `Won`, and `Lost`; `Won` is green and `Lost` is red
- Item winrate table no longer shows Avg K/D/A or derived KDA columns
- Item winrate table is sorted by highest item winrate first (ties by larger sample)
- Dashboard filter `Min matches per item` defaults to `3`
- Recent hero matches are displayed as a compact table below the item table
- Recent hero matches show final item slots only; timings are attached only to those final items when available from match details
- When final-item timings are available, recent-match items are ordered by earliest completion time
- Recent hero matches include `Net Worth` and player `Hero Damage`
- Recent hero matches show both `K/D/A` and per-match `KDA` rounded to one decimal
- Recent hero matches support incremental loading via `Load 10 more matches`
- Supports player input as account id or OpenDota profile URL
- Local `SQLite` storage for player match summaries
- Separate persisted storage for fetched match details
- Incremental summary sync to avoid repeated full-history calls
- Match details can be backfilled later without rebuilding summary history
- Graceful handling of missing OpenDota fields and rate limits

## Project entry points

- Web dashboard: `webapp/turbo_dashboard.py`
- CLI entry: `main.py`

## Requirements

- Python 3.12+
- Internet access

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
- `purchase_log` is often incomplete; purchased-item stats may have partial coverage.

## Troubleshooting

- `ModuleNotFoundError`: activate `.venv` and reinstall requirements.
- `OpenDotaRateLimitError`: wait and retry, reduce period, or use `OPENDOTA_API_KEY`.
- Empty/partial item data: this can happen due to OpenDota coverage limits; app will still show available data.
- After app updates, dashboard data schema is auto-refreshed; if values still look stale, click `Refresh Turbo Dashboard` again.
