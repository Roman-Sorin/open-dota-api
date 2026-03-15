# Turbo Buff App Guide

## What this app is

Turbo Buff is a Python application for analyzing your Dota 2 **Turbo-only** statistics via OpenDota.

The project includes two interfaces:

- **Web dashboard (recommended)**: Dotabuff-like personal analytics UI
- **CLI**: terminal commands for stats/items/matches and free-text query mode

## Main capabilities

- Turbo-only hero overview (matches, wins, losses, winrate, avg duration, avg net worth, avg damage, max kills, max hero damage)
- Hero Overview icons are clickable and can be used to select the hero without opening the dropdown
- Hero overview avg damage/net worth use match-detail fallback when player match rows don't include `hero_damage` or `net_worth`
- Dashboard summary cards: Turbo matches, wins, losses, winrate
- Time filter modes: `Days`, `Patches`, `Start Date`
- Dashboard sections load manually and independently to reduce one-shot API work on page open
- `Load Turbo Dashboard` fetches the hero overview only
- `Load Hero Details`, `Load Item Winrates`, and `Load Recent Matches` can each fetch the selected hero dataset on demand
- Per-hero detailed stats (avg K/D/A, KDA, avg duration, avg net worth, avg damage, max kills, max hero damage, Radiant/Dire WR)
- Most frequent final items
- Item winrate table (wins with item / matches with item), includes per-item match count
- Item winrate table is sorted by highest item winrate first (ties by larger sample)
- Dashboard filter `Min matches per item` defaults to `3`
- Recent hero matches are displayed as a compact table below the item table
- Recent hero matches show final item slots only; timings are attached only to those final items when available from match details
- Recent hero matches include `Net Worth` and player `Hero Damage`
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
- The app uses fallback match-detail calls for item enrichment and hero economy/damage enrichment when needed.
- Some requested metrics may depend on detail payload fields that are not guaranteed in every parsed match. When lane-specific data is unavailable, the app should prefer showing `-` instead of pretending the value is `0%`.
- `purchase_log` is often incomplete; purchased-item stats may have partial coverage.

## Troubleshooting

- `ModuleNotFoundError`: activate `.venv` and reinstall requirements.
- `OpenDotaRateLimitError`: wait and retry, reduce period, or use `OPENDOTA_API_KEY`.
- Empty/partial item data: this can happen due to OpenDota coverage limits; app will still show available data.
- After app updates, dashboard data schema is auto-refreshed; if values still look stale, click `Load Turbo Dashboard` again.
