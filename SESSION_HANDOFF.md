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
- Per-hero Turbo deep dive with avg damage and avg net worth
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

## 2026-04-02 research handoff: global hero item stats source feasibility

- User request under investigation:
  - replace personal `Item Winrates` with global hero item stats
  - target shape: `Item / WR / Matches`
  - strict requirement: `Turbo-only`
  - ideally tied to app filter semantics: `Days / Start Date / Patches`
- No app code was changed yet.
- Current status remains research-only.

### OpenDota findings

- Public OpenDota is not viable for this strict feature.
- `heroes/{hero_id}/itemPopularity` is not sufficient for the desired table.
- Public `explorer` can aggregate hero item stats in general, but current public data does not contain Turbo rows.
- Verified with SQL against public explorer:
  - `game_mode = 23` (`Turbo`) returned zero rows.
- Conclusion:
  - OpenDota public API cannot currently provide global `Turbo-only` hero item stats.

### STRATZ findings

- Important integration requirement discovered:
  - STRATZ GraphQL requests must include header `User-Agent: STRATZ_API`.
- Previous apparent token/API failure was caused by missing required `User-Agent`, not by an invalid token.
- With `Authorization: Bearer ...` plus `User-Agent: STRATZ_API`, STRATZ GraphQL works.
- Confirmed schema path:
  - root query type is `DotaQuery`
  - hero stats query is `heroStats`
  - item stats field is `heroStats.itemFullPurchase`
- Confirmed `heroStats.itemFullPurchase` returns the needed raw fields:
  - `itemId`
  - `matchCount`
  - `winCount`
  - `time`
  - `instance`
- This is enough to build:
  - item name/icon via constants lookup
  - `WR = winCount / matchCount`
  - `Matches = matchCount`
- Critical limitation confirmed from live schema introspection:
  - `heroStats.itemFullPurchase` args are only:
    - `heroId`
    - `week`
    - `bracketBasicIds`
    - `positionIds`
    - `minTime`
    - `maxTime`
    - `matchLimit`
  - it does **not** support:
    - `gameModeIds`
    - `gameVersionId` / patch filter
    - direct date range / start date filter
    - `lobbyTypeIds`
- STRATZ does expose `gameModeIds` on other hero winrate/trend fields such as:
  - `heroStats.winDay`
  - `heroStats.winWeek`
  - `heroStats.winMonth`
  - `heroStats.winGameVersion`
- But those are hero-level win stats, not item-level purchase stats.
- Conclusion:
  - STRATZ can support a weaker feature: global hero item stats in general.
  - STRATZ cannot currently satisfy the strict feature as requested:
    - `Turbo-only`
    - tied to app `Days / Start Date / Patches`

### Dotabuff findings

- Dotabuff hero item pages were fetched successfully through Cloudflare-capable clients during research.
- Hero item pages already expose the target table shape visually:
  - item
  - matches
  - win rate
- However, Turbo filtering for hero item pages is not yet proven.
- Testing with likely query params such as:
  - `mode=turbo`
  - `game_mode=23`
  - related variants
  did not produce a confirmed Turbo-specific result on hero item pages.
- Conclusion:
  - Dotabuff remains an unproven candidate for strict `Turbo-only` hero item stats.

### Current source decision

- Strict feature requirement (`global hero item stats` + `Turbo-only` + app time/patch filters) is still unresolved.
- Current source status:
  - `OpenDota`: not viable
  - `STRATZ`: partial only, not strict requirement
  - `Dotabuff`: still unconfirmed

### Recommended next step

- Continue source research instead of modifying the app.
- If product requirements are relaxed, STRATZ can be used later for a fallback feature:
  - global hero item stats without guaranteed Turbo/date/patch filtering.

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
- Item winrate and recent matches sections no longer depend on loading hero details first.

## 2026-03-08 deployment completion

- Streamlit Community Cloud app was deployed successfully.
- Stable production URL:
  - `https://open-dota-api-kzxvl2fznpz4cwwpfk2jmp.streamlit.app/`
- Added stable URL references to `README.md` and `DEPLOY.md`.

## 2026-04-03 production hotfix: pandas Styler compatibility

- Fixed a deployed dashboard crash in `Hero Overview` for patch-filter snapshots.
- Root cause:
  - the cloud/runtime environment hit a pandas `Styler` API mismatch at `hero_table_styler.applymap(...)`
  - traceback location was `webapp/turbo_dashboard.py`
- Added `webapp/styling.py` with one compatibility helper:
  - prefers `Styler.map(...)`
  - falls back to `Styler.applymap(...)`
- Routed both dashboard styled tables through that helper:
  - `Hero Overview`
  - `Item Winrates`
- Added regression coverage in `tests/test_styling.py` for both code paths:
  - runtime with `map`
  - runtime with only `applymap`
- Updated `README.md` and `APP_GUIDE.md` to document the styling compatibility rule.

## 2026-04-03 deployment hardening: pinned dependencies

- Replaced loose `>=` dependency ranges in `requirements.txt` with exact pins for the currently working environment.
- Purpose:
  - keep Streamlit Cloud restarts on the same dependency set
  - prevent unplanned pandas/Streamlit API drift from breaking a previously working deploy
- Current pinned versions:
  - `typer==0.24.1`
  - `requests==2.32.5`
  - `rich==14.3.3`
  - `python-dotenv==1.2.2`
  - `streamlit==1.55.0`
  - `pandas==2.3.3`
  - `pytest==9.0.2`
- Updated `README.md`, `APP_GUIDE.md`, and `DEPLOY.md` to document the exact-pin policy.

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

## 2026-03-08 patch-filter availability hotfix

- Relaxed patch-mode availability check in `webapp/turbo_dashboard.py`:
  - patch mode now depends on service capabilities (`get_patch_options` + overview support),
  - not blocked by strict `QueryFilters` field check.
- `patch_names` is injected into `QueryFilters` only when model supports it.
- Goal: remove false "temporarily unavailable" warning in production runtime.

## 2026-03-08 latest metric layout update

- Top summary metrics (`Turbo Matches`, `Turbo Wins`, `Turbo Winrate`) now use the same responsive flex card layout as detailed stats.
- On mobile, top metrics wrap to new rows based on available width (no fixed 3-column squeeze).

## 2026-03-08 patch filter root-cause fix

- Root cause of unstable patch dropdown behavior:
  - `DotaAnalyticsService` instance was created via `@st.cache_resource`.
  - After some deployments, Streamlit runtime could keep stale cached service object while UI code was newer.
  - This caused false runtime mismatch (`patch_names`/`get_patch_options` looked unavailable).
- Fix applied:
  - removed `@st.cache_resource` from service builder in `webapp/turbo_dashboard.py`.
  - patch capability checks now use safe runtime probing (`inspect` + `callable(getattr(...))`).
- Expected result:
  - Patch dropdown appears reliably when backend code supports it.

## 2026-03-08 patch filter hardening

- Added webapp-level patch timeline loader from OpenDota constants (`constants/patch`) independent of service helper method.
- Added local fallback filtering path for patch mode:
  - if runtime service does not support `patch_names` overview filtering,
  - app fetches Turbo matches and filters by selected patches in webapp logic,
  - hero overview and hero details still work for selected patches.
- Goal: patch multi-select works even under mixed/stale runtime code paths.

## 2026-03-08 production hotfix (bisect import) + patch-data note

- Fixed runtime error:
  - `Unexpected error: name 'bisect_right' is not defined`
  - Added missing import in `webapp/turbo_dashboard.py`:
    - `from bisect import bisect_right`
- Verified OpenDota patch constants payload currently contains only numeric patch names (e.g., `7.39`, `7.40`) and no lettered subpatch names (`a/b/c`).
- Implication:
  - lettered patch dropdown values cannot be sourced from OpenDota constants directly without an additional custom mapping/source.

## 2026-03-08 lettered patch source + column naming polish

- Patch dropdown now uses Valve patch feed as primary source:
  - `https://www.dota2.com/datafeed/patchnoteslist?language=english`
  - includes lettered subpatches (e.g., `7.39b`, `7.40b`, `7.40c`).
- OpenDota `constants/patch` kept as fallback source.
- Updated table column names to user-friendly labels without underscores:
  - Hero Overview: `Icon`, `Hero`, `Winrate`, `Avg K/D/A`, `KDA`, `Matches`, `Wins`, `Losses`, `Avg Kills`, `Avg Deaths`, `Avg Assists`.
  - Item table: `Icon`, `Item`, `Item Winrate`, `Matches With Item`, `Item Pick Rate`, `Wins With Item`.

## 2026-03-08 patch dropdown simplification

- Updated patch option builder logic:
  - lettered subpatches are shown only for the latest base patch series.
  - older base patches are shown as numeric patch names only.
- Example intent:
  - show `7.40`, `7.40b`, `7.40c`,
  - do not show old lettered entries like `7.39b`, `7.38c`, etc.

## 2026-03-08 rate-limit UX retry improvement

- Added user-friendly auto-retry flow for `OpenDotaRateLimitError` in web dashboard:
  - circular spinner + visible countdown (`5..1`) + progress bar.
  - automatic retry instead of immediate hard stop.
- Applied to key calls:
  - player profile check,
  - hero overview load,
  - patch-filtered match load,
  - hero matches load.
- Default behavior:
  - retry up to 2 times with 5-second cooldown between attempts.

## 2026-03-08 patch multiselect interaction fix

- Fixed issue where selecting an additional patch in multiselect required two clicks.
- Root cause:
  - widget was re-initialized via `default=...` on reruns, causing first selection to be overwritten.
- Fix:
  - switched patch multiselect to stateful widget key (`patches_widget_selection`),
  - keep widget selection sanitized against current options list,
  - preserve immediate single-click add/remove behavior.

## 2026-03-08 patch option labels with date ranges

- Updated patch multiselect labels to include patch active range:
  - format: `PatchName (YYYY-MM-DD - YYYY-MM-DD)`
  - for latest patch: `... - now`
- Filter values still use pure patch names internally; only display labels changed.

## 2026-03-08 patch multiselect label UX tweak

- Implemented UI behavior:
  - dropdown option rows keep full labels with date ranges.
  - selected tags in multiselect are shortened to patch name only.
- Technical note:
  - done via lightweight frontend script because native Streamlit multiselect applies one label format to both options and selected tags.

## 2026-03-08 patch selector stability update

- Replaced JS-based label hack with stable native Streamlit flow:
  - `Selected Patches` multiselect shows patch names only (no dates).
  - `Add Patch (with dates)` dropdown shows patch name + date range labels.
  - choosing patch in dropdown appends it to selected list and resets dropdown.
- Rationale:
  - avoids DOM patching fragility on Streamlit Cloud.

## 2026-03-08 patch UI rollback

- Rolled back patch selector UI to simpler version per user request:
  - single `Patches (multi-select)` control only,
  - patch names only (no date labels, no extra add dropdown).

## 2026-03-08 item winrates table update

- Reworked `Item Winrates` columns in dashboard:
  - kept: `Icon`, `Item`, `Item Winrate`
  - replaced old extra columns with:
    - `Avg K/D/A` (for matches where item appears)
    - `KDA` (for matches where item appears)
- Service layer (`get_item_winrates`) now computes per-item average kills/deaths/assists and KDA.

## 2026-03-08 hotfix: item winrate KeyError compatibility

- Fixed runtime `KeyError: 'avg_kills_with_item'` in dashboard table rendering.
- Cause:
  - mixed runtime/old row schema could return item rows without new per-item KDA fields.
- Fix:
  - UI now uses safe `.get(..., 0.0)` fallbacks for `avg_kills_with_item`, `avg_deaths_with_item`, `avg_assists_with_item`, `kda_with_item`.

## 2026-03-08 hotfix: item KDA zeros in mixed runtime

- Added compatibility augmenter in `webapp/turbo_dashboard.py`:
  - if item rows come without per-item KDA fields, app now reconstructs per-item Avg K/D/A and KDA from loaded matches.
  - avoids `0/0/0` and `0` output caused by schema mismatch in mixed runtime states.
- Fallback behavior:
  - if per-item summary slots are missing for an item, app uses global match averages instead of hard zeros.

## 2026-03-08 fix: per-item KDA must differ by item

- Improved compatibility augmenter for item KDA calculation:
  - now reconstructs item presence per match using summary slots plus match-details fallback (player row extraction),
  - then computes Avg K/D/A and KDA strictly on matches where each item appears.
- Result:
  - item KDA values are no longer uniformly equal to global hero averages in normal cases.

## 2026-03-08 select-hero UX update

- Improved `Select Hero` usability:
  - dropdown options now include hero name + matches + WR + KDA in a consistent readable format.
  - added hero preview card right below selector with hero icon and key stats.
- Note:
  - native Streamlit `selectbox` does not support inline images inside option rows.
  - image is shown in preview directly under dropdown for selected hero.

## 2026-03-08 production hotfix (NameError)

- Fixed `NameError: datetime is not defined` in `webapp/turbo_dashboard.py`.
- Cause:
  - patch timeline parser used `datetime.fromisoformat(...)` without importing `datetime`.
- Fix:
  - added `from datetime import datetime` import.

## 2026-03-08 hero overview KDA presentation update

- Added combined `Avg K/D/A` column in `Hero Overview` right after `Winrate`.
- Format is `kills/deaths/assists` (e.g., `11/6/10`) using rounded averages.
- Existing separate `avg_kills`, `avg_deaths`, `avg_assists` columns remain at the end.

## 2026-03-15 manual section loading update

- Removed the one-time automatic dashboard load on first page open.
- Dashboard loading is now split into explicit buttons:
  - `Load Turbo Dashboard` loads only the overview/filter result.
- `Load Hero Details` loads the selected hero's filtered match set and stat cards.

## 2026-03-15 hero economy + independent section loading update

- Added average net worth to Turbo hero overview and detailed hero stat cards.
- Hero Overview column label shortened from `Average Net Worth` to `Avg NW`.
- Recent hero matches and CLI match rows now surface per-match net worth.
- `Load Hero Details`, `Load Item Winrates`, and `Load Recent Matches` now resolve hero matches independently instead of blocking on each other.
- Added request-level caching for player match-list queries with TTLs tuned by recency to cut repeated OpenDota API calls.
- Bumped overview schema version so stale Streamlit sessions refresh after the new economy metrics shipped.
- Added regression coverage for avg net worth formulas and cached historical match loading.

## 2026-03-15 sqlite match store + hero overview interaction update

- Added `utils/match_store.py` with persisted `SQLite` storage for player match summaries, match details, and sync state.
- Web app and CLI now construct `DotaAnalyticsService` with the local match store.
- Summary history is synced incrementally per player/game-mode instead of refetching full history every reload.
- Match details are stored separately and reused for economy/item enrichment.
- Added service-level `backfill_match_details(...)` hook for future explicit full-detail sync workflows.
- Added Hero Overview metrics:
  - `Avg Duration`
  - `Max Kills`
  - `Max Damage`
- Detailed Turbo Stats now show:
  - `Avg Duration`
  - `Max Kills`
  - `Max Damage`
- Attempted clickable hero icons in `Hero Overview` were reverted because they broke dataframe interactions like sorting/filtering/resizing.
- Hero metric fields in `Hero Overview` and `Detailed Turbo Stats` should now be maintained from one shared UI definition, not two separate hardcoded lists.
- User preference: after push, do not spend time on automated deployed-build verification; user checks deploy manually.
- User preference: keep product/UX directives recorded in Markdown handoff/docs files.
- User preference: section UX should feel persistent and human; when switching heroes, already loaded sections should reopen from cache instead of requiring repeated `Load ...` clicks.
- Local OpenDota reference dump for future code-agent work:
  - `open_dota_api_docs.txt.txt`
  - `Load Item Winrates` and `Load Recent Matches` load those heavier sections only when clicked.
- Added request-key-based section state tracking so hero/item/recent sections do not display stale data after hero/filter changes.
- Bumped `OVERVIEW_SCHEMA_VERSION` to `6` so old session overview data is cleared after deploy.
- Added regression tests for dashboard request-key normalization and invalidation behavior in `tests/test_dashboard_state.py`.

## 2026-03-15 hero overview single-source stats fix

- Fixed a real inconsistency where `Hero Overview` could show `Rad WR` / `Dire WR` as `0%` while `Detailed Turbo Stats` showed correct values for the same hero.
- Root cause: hero overview still had a second aggregation path in `webapp/turbo_dashboard.py`, while detail cards used `service.build_stats(...)`.
- Added `DotaAnalyticsService.build_turbo_hero_overview_rows(...)` and moved hero-overview row construction to the service layer.
- `get_turbo_hero_overview(...)` now returns rows from that shared builder.
- Patch-filter fallback in the Streamlit UI now also calls the same shared service builder instead of maintaining a duplicate overview aggregation in the UI.
- Bumped `OVERVIEW_SCHEMA_VERSION` to `9` so stale session overview rows are invalidated after deploy.
- Added regression coverage proving overview side-winrate values match detailed hero stats for the same match set.
- User preference reminder: push after each completed code change, and keep Markdown docs current for code agents.

## 2026-03-15 cached dashboard autoload update

- Added service methods for cache-only reads from the SQLite match store:
  - `get_cached_matches(...)`
  - `get_cached_sync_state(...)`
  - `get_cached_turbo_hero_overview(...)`
- Streamlit dashboard now auto-restores `Hero Overview` from local SQLite data when the current player/filter combination already has cached Turbo matches.
- This cache-only restore does not call OpenDota and does not spend API quota.
- Top button label changed from `Load Turbo Dashboard` to `Refresh Turbo Dashboard`.
- When overview is restored from cache only, the UI now shows a caption explaining that it is local cached data and that `Refresh Turbo Dashboard` will sync newer matches.
- Added regression coverage proving cached hero overview can be built from SQLite without any API calls.

## 2026-03-26 default patch filter preset update

- Changed the first-load dashboard default from `Days` mode to `Patches` mode.
- Default patch selection now targets patch family `7.41`:
  - select `7.41`
  - also select any available `7.41x` letter patches such as `7.41b` / `7.41c`
- Added a pure helper in `webapp/filter_defaults.py` so the default selection rule is unit-tested without importing the full Streamlit page.
- Added regression tests in `tests/test_filter_defaults.py` for both the `7.41` family selection and the fallback when no `7.41` option exists.

## 2026-03-26 default hero preset update

- Changed the default selected hero in the overview hero dropdown from `Wraith King` to `Spectre`.
- Added a pure helper in `webapp/hero_defaults.py` so default-hero selection stays testable without importing the Streamlit page.
- Added regression tests in `tests/test_hero_defaults.py` for Spectre preference and first-option fallback behavior.

## 2026-03-30 default hero preset revert

- Changed the default selected hero in the overview hero dropdown from `Spectre` back to `Wraith King`.
- Updated `tests/test_hero_defaults.py` so the pure helper regression coverage now prefers `Wraith King` and still falls back to the first available hero when `Wraith King` is absent.

## 2026-04-01 default hero preset update

- Changed the default selected hero in the overview hero dropdown from `Wraith King` to `Spectre`.
- Updated `tests/test_hero_defaults.py` so the pure helper regression coverage now prefers `Spectre` and still falls back to the first available hero when `Spectre` is absent.

## 2026-04-04 recent-match item timing legacy-cache fix

- Root cause: some cached `match_details` rows existed but were legacy/incomplete for the selected player because they lacked `purchase_log`; recent matches and item coverage then treated those rows as complete and rendered `-` timings indefinitely.
- Added centralized detail-hydration targeting in `services/analytics_service.py` so main dashboard refreshes re-fetch both truly missing details and legacy cached rows missing the selected-player `purchase_log`.
- Added regression coverage in `tests/test_match_store.py` for the reported Spectre-style timing case (`Phylactery 8m`, `Orchid 12m`, `Manta 15m`, `Aegis 17m`, `Skadi 20m`) plus a cache-path `load_match_snapshot(..., hydrate_details=True)` test proving stale stored details are repaired from cache-backed snapshots too.
- Updated `APP_GUIDE.md` to document that a main dashboard refresh can repair legacy cached item timings without hidden section-level detail fetches.
- Follow-up UI fix in `webapp/turbo_dashboard.py`: centralized recent-section snapshot writes and made `Refresh Turbo Dashboard` rebuild an already-visible `Recent Matches` section from cached data in the same rerun, so repaired timings are not hidden behind stale section session state.

## 2026-03-26 reported bad-match exclusion

- Excluded reported match `8743652071` centrally via `utils/match_filters.py`.
- The shared exclusion path is enforced inside `DotaAnalyticsService._parse_match_summary_row(...)`, so it applies to:
  - SQLite-backed cached reads
  - direct OpenDota fetches
  - overview/detail/item/matchup/recent-match sections that consume normalized match summaries
- Added regression coverage in `tests/test_match_filters.py` for both direct-client and SQLite-backed match paths using the exact reported match id.

## 2026-03-27 reported bad-match exclusion follow-up

- Added reported match `8745970611` to the same centralized exclusion set in `utils/match_filters.py`.
- Expanded `tests/test_match_filters.py` so both centralized fetch paths still exclude both reported ids:
  - direct OpenDota-style client results
  - SQLite-backed cached match reads
- Updated user-facing docs (`README.md`, `APP_GUIDE.md`) so the known excluded-match list stays current.
