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
  - default baseline/start is `2026-01-21`
- Hero overview in Turbo (matches, won matches, lost matches, WR, avg K/D/A, avg duration, avg net worth, avg damage, KDA, max kills, max hero damage)
- Hero overview highlights won matches in green and lost matches in red
- Hero Overview column labels stay short and English-only: `All`, `Won`, `Lost`, `WR`, `Dur`, `NW`, `Dmg`
- All winrates in the UI use the same colors: below `50%` red, exactly `50%` yellow, above `50%` green
- Hero overview and detailed hero stats now share one metric-definition source in the UI, so added hero fields stay aligned in both places
- Hero overview aggregation now also comes from one shared service-side stats source, so values like `Rad WR` and `Dire WR` stay identical between overview and detailed hero stats
- When Turbo match rows miss `hero_damage` or `net_worth`, the app enriches overview/detail stats from match details stored locally
- Cached Hero Overview now also enriches missing `hero_damage` and `net_worth` from stored match details, so heroes do not stay stuck at zero when the local summary rows were incomplete
- Top dashboard metrics include Turbo matches, wins, losses, and winrate
- Dashboard loading is manual by section:
  - cached overview data can auto-open from local SQLite storage when available
  - `Refresh Turbo Dashboard` syncs overview data from OpenDota when you want newer matches
  - `Refresh Hero Details`, `Refresh Item Winrates`, and `Refresh Recent Matches` rebuild from the currently loaded dashboard snapshot for the selected hero
- Section refreshes no longer pull newer matches than the currently loaded overview; only `Refresh Turbo Dashboard` advances the dataset
- `Refresh Turbo Dashboard` now forces an incremental sync check for new matches only; already cached summaries and match details are reused instead of being re-fetched
- Detailed hero section in Turbo includes avg duration, avg damage, avg net worth, max kills, and max hero damage
- Selected-hero section refreshes are grouped into one action bar above the sections (`Hero Details`, `Matchups`, `Item Winrates`, `Recent Matches`)
- Matchups section now uses the same two-table layout everywhere: `Allies` and `Opponents`
  - Both `Selected Hero` and `All Heroes` show the same column order: `Hero Icon / Hero / WR / Matches / Won / Lost`
  - In Matchups, only `WR` is color-coded; `Won` and `Lost` stay neutral
  - Matchup winrates remain numeric under the hood so both built-in sorting and user-click sorting treat `100.00` correctly
  - Changing `Min matchup matches` only filters the already built matchup snapshot; it does not require pressing `Refresh Matchups` again
- Experimental Hero Trends stays at the bottom and currently shows daily trends for the selected hero
- Hero detail, item stats, and recent matches stay cached per hero/filter in the current session when you switch between heroes
- Detail-section caches are scoped to the current dashboard snapshot so old hero/recent/item rows are not reused after the overview changes
- Section actions are refresh actions now; if dashboard data is newer than a section cache, the UI shows a stale hint instead of silently hiding that fact
- Hero Overview snapshots with suspicious per-hero zero `NW`/`Dmg`/`Max Dmg` rows are auto-invalidated and rebuilt instead of being rendered as valid data
- Item winrates (when item appears in final slots), with match count shown
- Item winrates no longer show Avg K/D/A or derived KDA columns
- Recent hero matches shown as a compact one-row-per-match table under the item table
- Recent hero matches show only final slots, and item timings are shown only when the final item completion time is available
- When final-item timings are available, recent-match items are ordered by earliest completion time
- Recent hero matches include `Net Worth` and player `Hero Damage`
- Recent hero matches show both `K/D/A` and per-match `KDA` rounded to one decimal
- Recent hero matches support `Load 10 more matches`
- Item winrates are ordered by highest winrate first (then by match count)
- Default minimum matches per item in the dashboard filter is `3`
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

Set key only if needed:

```env
OPENDOTA_API_KEY=
```

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
- The app falls back to `matches/{match_id}` for final slots if needed.
- Player matches are persisted in local `SQLite` storage and reused for later filters/analytics.
- Match details are persisted separately and reused for enrichment-heavy sections.
- The service performs incremental syncs instead of refetching whole history on each reload.
- `purchase_log` is often incomplete, so purchased-item analytics may cover only part of matches.
- Without API key, rate limits can be hit.

## Tests

```bash
pytest -q
```

## Collaboration Rules

- After completing any implementation change, update relevant Markdown docs (`README.md`, `APP_GUIDE.md`, etc.) when behavior, UX, setup, or workflows changed.
- After changes are complete and validated, commit and push to the remote branch in the same working session.
