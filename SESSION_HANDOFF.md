# Application Handoff Notes

## Current product direction

Primary UX is now a Turbo-only web dashboard (Streamlit) that acts like a personal Dotabuff view.
CLI remains available as a secondary interface.

## Entry points

- Web dashboard: `streamlit run webapp/turbo_dashboard.py`
- CLI: `main.py` -> Typer app in `cli/commands.py`

## Dashboard capabilities

- Turbo-only hero overview across selected period
- Time filter supports:
  - days period
  - multi-select patch list (OpenDota patch constants)
- Per-hero Turbo deep dive
- Item winrate table (`wins with item / matches with item` based on final slots)

## Data caveats implemented

- For many Turbo rows, `players/{id}/matches` may return empty item slots.
  - Implemented fallback to `matches/{match_id}` per match for item extraction.
- `purchase_log` is partial.
  - Purchased-item percentages in CLI are computed against total filtered matches and annotated with coverage.

## API layer

`clients/opendota_client.py` methods:
- `get_player_profile`
- `get_player_matches`
- `get_player_recent_matches`
- `get_player_heroes`
- `get_constants_heroes`
- `get_constants_items`
- `get_match_details`

## Service layer additions

`services/analytics_service.py` includes:
- `get_turbo_hero_overview`
- `get_item_winrates`
- robust fallback for missing summary item slots

## Parser updates

- Fixed intent bug where `последние 2 месяца` incorrectly set `limit=2`
- Added RU aliases for common heroes (e.g., `фантомка`, `па`, `цк`, `ам`, `вк`)
- Item-intent now has priority when query includes purchase/item vocabulary

## Suggested next upgrades

- Add charts (WR by hero, trends by week)
- Add role/lane breakdown for Turbo
- Add item pair/synergy winrates
- Add caching for match detail calls (beyond constants)

## 2026-03-08 session updates

- Added mobile-focused Streamlit CSS tweaks in `webapp/turbo_dashboard.py`.
- Small-screen padding reduced for better phone readability.
- Metric cards made more compact on mobile.
- Dataframes configured for horizontal scrolling on narrow screens.
- Added `.streamlit/config.toml` with cloud/headless-friendly defaults.
- Added `DEPLOY.md` with deployment options.
- Included quick free phone access workflow via LocalTunnel.
- Included permanent free hosting workflow via Streamlit Community Cloud.
- Added hero-level filter in dashboard: `Min matches per hero`.
- Hero table and hero selector now respect hero minimum matches threshold.
- Added UX handling for empty hero set after hero threshold filter.
- Updated `.gitignore` with `.runlogs/` and `.streamlit/secrets.toml`.
- Initialized git repository and created initial commit:
  - `294cda9 Initial project import and Streamlit dashboard updates`
- Added Cloudflare Tunnel deployment flow to `DEPLOY.md` (works in current network).
- Verified app external access via Cloudflare Tunnel URL (HTTP 200 during session).

## Change logging rule (important)

- From now on, every code/config/deploy change must be recorded in this file (`SESSION_HANDOFF.md`) in the same session.
- Purpose: allow any next agent session to recover project state by reading this file first.

## Current deployment status

- Stable Streamlit Community Cloud app is live:
  - `https://open-dota-api-kzxvl2fznpz4cwwpfk2jmp.streamlit.app/`
- Auto-deploy is enabled by Streamlit Cloud integration:
  - every push to `main` in `Roman-Sorin/open-dota-api` triggers redeploy automatically.
- Cloudflare quick tunnel can still be used as temporary fallback when needed.

## 2026-03-08 follow-up deployment updates

- Installed GitHub CLI (`gh`) and authenticated as `Roman-Sorin`.
- Created new GitHub repository and pushed current branch:
  - `https://github.com/Roman-Sorin/open-dota-api`
- Configured local `origin` remote to the repository above.
- Re-launched Streamlit + Cloudflare quick tunnel for phone access.
- Current temporary URL in this session:
  - `https://sub-required-apparently-rugs.trycloudflare.com`
  - Verified reachable (HTTP 200) at update time.
- Remaining step for stable permanent URL:
  - Create Streamlit Community Cloud app linked to `Roman-Sorin/open-dota-api` with main file `webapp/turbo_dashboard.py`.

## 2026-03-08 UI updates (latest)

- Removed `Most Frequent Final Items` section from `webapp/turbo_dashboard.py`.
- Removed related `build_items(...)` calculation and note caption, since this section is no longer shown.
- Item winrate and recent matches sections remain unchanged.

## 2026-03-08 deployment completion

- Streamlit Community Cloud app was deployed successfully.
- Stable production URL:
  - `https://open-dota-api-kzxvl2fznpz4cwwpfk2jmp.streamlit.app/`
- Added stable URL references to `README.md` and `DEPLOY.md`.

## 2026-03-08 latest dashboard simplification

- Rounded all displayed numeric values to whole numbers in dashboard UI:
  - winrates, KDA, averages, and item percentage columns.
- Removed `Recent Turbo Matches` section from `webapp/turbo_dashboard.py`.
- Removed unused `build_match_rows(...)` call after deleting recent matches section.

## 2026-03-08 latest UX update

- Added one-time automatic dashboard load on first app open:
  - `Load Turbo Dashboard` request now runs automatically once when the page opens.
  - Manual button remains for explicit reloads after changing filters.

## 2026-03-08 latest time-filter update

- Added time filter mode toggle in dashboard sidebar:
  - `Days` (existing behavior)
  - `Patches` (new, multi-select)
- Added OpenDota patch constants loading (`constants/patch`) via client + cache.
- Added match-level filtering by selected patch names in service layer.
- Hero overview and detailed hero stats now honor selected patches when patch mode is active.

## 2026-03-08 production hotfix (patch-mode compatibility)

- Added defensive compatibility logic in `webapp/turbo_dashboard.py`:
  - detect whether running service/query model supports patch filtering.
  - only pass `patch_names` when support is available.
  - fallback to `Days`-only mode instead of crashing on mixed/stale deployments.
- Purpose: prevent runtime errors like:
  - `unexpected keyword argument 'patch_names'`
  - missing `get_patch_options` attribute

## 2026-03-08 latest UI polish

- Item winrate table column order updated:
  - now `item_image` -> `item` -> `item_winrate_%` -> other columns.
- Hero overview column order updated:
  - moved `kda` near the beginning (right after hero name).
- Formatting update:
  - winrate values now render with explicit `%` in tables/metrics.
  - only `KDA` values render with one decimal place (`x.x`).
  - other numeric values remain integer-rounded.
- Replaced detailed stats `st.columns` rows with responsive wrapped metric cards
  - mobile now keeps stats in a single wrapping flow instead of separate fixed rows.

## 2026-03-08 latest filter/columns adjustment

- `Time filter mode` now always shows both options: `Days` and `Patches`.
- If patch filtering is unavailable in runtime, app shows warning instead of hiding the option.
- `Hero Overview` column order adjusted again:
  - `winrate` moved to the 4th column (after `hero_image`, `hero`, `kda`).
