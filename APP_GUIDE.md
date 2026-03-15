# Turbo Buff App Guide

## What this app is

Turbo Buff is a Python application for analyzing your Dota 2 **Turbo-only** statistics via OpenDota.

The project includes two interfaces:

- **Web dashboard (recommended)**: Dotabuff-like personal analytics UI
- **CLI**: terminal commands for stats/items/matches and free-text query mode

## Main capabilities

- Turbo-only hero overview (matches, wins, losses, winrate, avg damage)
- Hero overview avg damage uses match-detail fallback when player match rows don't include `hero_damage`
- Dashboard summary cards: Turbo matches, wins, losses, winrate
- Time filter modes: `Days`, `Patches`, `Start Date`
- Dashboard sections load manually to reduce one-shot API work on page open
- `Load Turbo Dashboard` fetches the hero overview only
- `Load Hero Details` fetches matches and the detailed hero stat cards
- `Load Item Winrates` and `Load Recent Matches` fetch those heavier sections only when clicked
- Per-hero detailed stats (avg K/D/A, KDA, Radiant/Dire WR)
- Most frequent final items
- Item winrate table (wins with item / matches with item), includes per-item match count
- Item winrate table is sorted by highest item winrate first (ties by larger sample)
- Dashboard filter `Min matches per item` defaults to `3`
- Recent hero matches are displayed as a compact table below the item table
- Recent hero matches show final item slots only; timings are attached only to those final items when available from match details
- Recent hero matches include `Net Worth` and player `Hero Damage`
- Recent hero matches support incremental loading via `Load 10 more matches`
- Supports player input as account id or OpenDota profile URL
- Caching for constants and match details
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
- The app uses fallback match-detail calls for item enrichment when needed.
- `purchase_log` is often incomplete; purchased-item stats may have partial coverage.

## Troubleshooting

- `ModuleNotFoundError`: activate `.venv` and reinstall requirements.
- `OpenDotaRateLimitError`: wait and retry, reduce period, or use `OPENDOTA_API_KEY`.
- Empty/partial item data: this can happen due to OpenDota coverage limits; app will still show available data.
- After app updates, dashboard data schema is auto-refreshed; if values still look stale, click `Load Turbo Dashboard` again.
