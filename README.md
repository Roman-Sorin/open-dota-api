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
- Hero overview in Turbo (matches, WR, avg K/D/A, avg net worth, avg damage, KDA)
- When Turbo match rows miss `hero_damage` or `net_worth`, the app enriches overview/detail stats from match details with cache-backed fallback
- Top dashboard metrics include Turbo matches, wins, losses, and winrate
- Dashboard loading is manual by section:
  - `Load Turbo Dashboard` loads the overview only
  - `Load Hero Details`, `Load Item Winrates`, and `Load Recent Matches` can each be loaded independently for the selected hero
- Detailed hero section in Turbo includes avg damage and avg net worth
- Item winrates (when item appears in final slots), with match count shown
- Recent hero matches shown as a compact one-row-per-match table under the item table
- Recent hero matches show only final slots, and item timings are shown only when the final item completion time is available
- Recent hero matches include `Net Worth` and player `Hero Damage`
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
- Historical player-match list responses are cached with longer TTLs than very recent ranges to reduce repeated OpenDota requests.
- `purchase_log` is often incomplete, so purchased-item analytics may cover only part of matches.
- Without API key, rate limits can be hit.

## Tests

```bash
pytest -q
```

## Collaboration Rules

- After completing any implementation change, update relevant Markdown docs (`README.md`, `APP_GUIDE.md`, etc.) when behavior, UX, setup, or workflows changed.
- After changes are complete and validated, commit and push to the remote branch in the same working session.
