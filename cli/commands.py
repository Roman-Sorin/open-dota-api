from __future__ import annotations

import typer

from clients.opendota_client import OpenDotaClient
from formatters.output_formatter import TerminalFormatter
from models.dtos import Intent, QueryFilters
from parsers.input_parser import find_hero_by_name, parse_ask_query, parse_days, parse_mode
from services.analytics_service import DotaAnalyticsService
from utils.cache import JsonFileCache
from utils.config import get_cache_dir, get_settings
from utils.exceptions import OpenDotaError, OpenDotaNotFoundError, OpenDotaRateLimitError, ValidationError
from utils.helpers import parse_player_id


app = typer.Typer(help="OpenDota CLI analyzer")


def _build_service() -> tuple[DotaAnalyticsService, TerminalFormatter]:
    settings = get_settings()
    client = OpenDotaClient(
        base_url=settings.base_url,
        timeout_seconds=settings.timeout_seconds,
        api_key=settings.api_key,
    )
    cache = JsonFileCache(cache_dir=get_cache_dir(), ttl_hours=settings.cache_ttl_hours)
    service = DotaAnalyticsService(client=client, cache=cache)
    formatter = TerminalFormatter()
    return service, formatter


def _parse_mode_arg(mode: str | None) -> tuple[int, str] | None:
    if not mode:
        return None
    result = parse_mode(mode)
    if result:
        return result
    raise ValidationError(f"Unsupported mode '{mode}'. Supported: turbo/турбо")


def _build_filters(
    service: DotaAnalyticsService,
    player: str,
    hero: str | None,
    mode: str | None,
    days: int | None,
    limit: int = 20,
) -> QueryFilters:
    player_id = parse_player_id(player)
    hero_id = None
    hero_name = None

    if hero:
        hit = find_hero_by_name(hero, service.references.hero_parser)
        hero_id = hit.hero_id
        hero_name = hit.hero_name

    mode_hit = _parse_mode_arg(mode)
    safe_days = parse_days(days)

    return QueryFilters(
        player_id=player_id,
        hero_id=hero_id,
        hero_name=hero_name,
        game_mode=mode_hit[0] if mode_hit else None,
        game_mode_name=mode_hit[1] if mode_hit else None,
        days=safe_days,
        limit=limit,
    )


def _run_stats(service: DotaAnalyticsService, formatter: TerminalFormatter, filters: QueryFilters) -> None:
    service.ensure_player_exists(filters.player_id)
    matches = service.fetch_matches(filters)

    hero_label = filters.hero_name or service.resolve_hero_name(filters.hero_id)
    formatter.print_context(filters, hero_label)

    if not matches:
        formatter.print_no_matches()
        return

    stats = service.build_stats(matches)
    formatter.print_stats(stats)


def _run_items(service: DotaAnalyticsService, formatter: TerminalFormatter, filters: QueryFilters) -> None:
    service.ensure_player_exists(filters.player_id)
    matches = service.fetch_matches(filters)

    hero_label = filters.hero_name or service.resolve_hero_name(filters.hero_id)
    formatter.print_context(filters, hero_label)

    if not matches:
        formatter.print_no_matches()
        return

    items = service.build_items(filters.player_id, matches)
    formatter.print_items(items)


def _run_matches(service: DotaAnalyticsService, formatter: TerminalFormatter, filters: QueryFilters) -> None:
    service.ensure_player_exists(filters.player_id)
    matches = service.fetch_matches(filters, limit=filters.limit)

    hero_label = filters.hero_name or service.resolve_hero_name(filters.hero_id)
    formatter.print_context(filters, hero_label)

    if not matches:
        formatter.print_no_matches()
        return

    rows = service.build_match_rows(filters.player_id, matches, limit=filters.limit)
    formatter.print_matches(rows)


def _handle_errors(formatter: TerminalFormatter, exc: Exception) -> None:
    if isinstance(exc, OpenDotaNotFoundError):
        formatter.print_error("Player or resource was not found in OpenDota")
    elif isinstance(exc, OpenDotaRateLimitError):
        formatter.print_error("OpenDota rate limit reached. Retry later or provide OPENDOTA_API_KEY.")
    elif isinstance(exc, ValidationError):
        formatter.print_error(str(exc))
    elif isinstance(exc, OpenDotaError):
        formatter.print_error(str(exc))
    else:
        formatter.print_error(f"Unexpected failure: {exc}")


@app.command()
def stats(
    player: str = typer.Option(..., help="Player id or OpenDota profile URL"),
    hero: str | None = typer.Option(None, help="Hero name, e.g. 'Chaos Knight' or 'CK'"),
    mode: str | None = typer.Option(None, help="Game mode, e.g. turbo"),
    days: int | None = typer.Option(60, help="Lookback period in days"),
) -> None:
    """Show general performance stats for filtered matches."""
    service, formatter = _build_service()
    try:
        filters = _build_filters(service, player, hero, mode, days)
        _run_stats(service, formatter, filters)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(formatter, exc)
        raise typer.Exit(code=1)


@app.command()
def items(
    player: str = typer.Option(..., help="Player id or OpenDota profile URL"),
    hero: str | None = typer.Option(None, help="Hero name, e.g. 'Chaos Knight' or 'CK'"),
    mode: str | None = typer.Option(None, help="Game mode, e.g. turbo"),
    days: int | None = typer.Option(60, help="Lookback period in days"),
) -> None:
    """Show item frequency for filtered matches."""
    service, formatter = _build_service()
    try:
        filters = _build_filters(service, player, hero, mode, days)
        _run_items(service, formatter, filters)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(formatter, exc)
        raise typer.Exit(code=1)


@app.command()
def matches(
    player: str = typer.Option(..., help="Player id or OpenDota profile URL"),
    hero: str | None = typer.Option(None, help="Hero name, e.g. 'Chaos Knight' or 'CK'"),
    mode: str | None = typer.Option(None, help="Game mode, e.g. turbo"),
    days: int | None = typer.Option(60, help="Lookback period in days"),
    limit: int = typer.Option(20, help="Number of rows to show"),
) -> None:
    """Show latest filtered matches."""
    service, formatter = _build_service()
    try:
        filters = _build_filters(service, player, hero, mode, days, limit=max(1, min(limit, 100)))
        _run_matches(service, formatter, filters)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(formatter, exc)
        raise typer.Exit(code=1)


@app.command()
def ask(query: str = typer.Argument(..., help="Natural language query")) -> None:
    """Parse free-form query and route it to stats/items/matches."""
    service, formatter = _build_service()
    try:
        parsed = parse_ask_query(query, service.references.hero_parser)
        filters = parsed.filters
        if filters.days is None:
            filters.days = 60
        if filters.game_mode_name is None and filters.game_mode == 23:
            filters.game_mode_name = "Turbo"

        if parsed.intent == Intent.STATS:
            _run_stats(service, formatter, filters)
            return
        if parsed.intent == Intent.ITEMS:
            _run_items(service, formatter, filters)
            return

        _run_matches(service, formatter, filters)
    except Exception as exc:  # noqa: BLE001
        _handle_errors(formatter, exc)
        raise typer.Exit(code=1)
