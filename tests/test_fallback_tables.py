from webapp.fallback_tables import (
    HERO_PORTRAIT_ASPECT_RATIO,
    HERO_PORTRAIT_BORDER_RADIUS_PX,
    HERO_PORTRAIT_COLUMN_WIDTH_PX,
    HERO_PORTRAIT_WIDTH_PX,
    HERO_TABLE_ROW_HEIGHT_PX,
    build_hero_portrait_html,
    build_sortable_html_table,
    hero_overview_fallback_headers,
    matchup_fallback_headers,
)


def test_fallback_table_hero_portrait_contract_matches_recent_matches_reference() -> None:
    assert HERO_PORTRAIT_WIDTH_PX == 56
    assert HERO_PORTRAIT_ASPECT_RATIO == "16 / 9"
    assert HERO_PORTRAIT_BORDER_RADIUS_PX == 6
    assert HERO_PORTRAIT_COLUMN_WIDTH_PX == 72
    assert HERO_TABLE_ROW_HEIGHT_PX == 40

    portrait_html = build_hero_portrait_html("spectre.png", "Spectre")
    assert 'class="hero-portrait-wrap"' in portrait_html
    assert 'src="spectre.png"' in portrait_html
    assert 'alt="Spectre"' in portrait_html


def test_hero_overview_fallback_headers_keep_sorting_for_non_icon_columns() -> None:
    headers = hero_overview_fallback_headers(
        hero_matches_column="All",
        hero_wins_column="Won",
        hero_losses_column="Lost",
    )

    assert headers[0] == {"label": "Icon", "type": "text", "sortable": False}
    assert all(bool(header["sortable"]) for header in headers[1:])


def test_matchup_fallback_headers_keep_sorting_for_non_icon_columns() -> None:
    headers = matchup_fallback_headers()

    assert headers[0] == {"label": "Icon", "type": "text", "sortable": False}
    assert [header["label"] for header in headers[1:]] == ["Hero", "WR", "Matches", "Won", "Lost"]
    assert all(bool(header["sortable"]) for header in headers[1:])


def test_sortable_html_table_emits_sortable_headers_and_client_sorting_script() -> None:
    html, height = build_sortable_html_table(
        table_id="matchups-fallback",
        headers=matchup_fallback_headers(),
        rows=[
            [
                {"display_html": build_hero_portrait_html("axe.png", "Axe"), "sort_value": "Axe", "class_name": "hero-portrait-cell"},
                {"display_html": "Axe", "sort_value": "Axe"},
                {"display_html": "75.00%", "sort_value": 75.0, "class_name": "num"},
                {"display_html": "4", "sort_value": 4, "class_name": "num"},
                {"display_html": "3", "sort_value": 3, "class_name": "num"},
                {"display_html": "1", "sort_value": 1, "class_name": "num"},
            ]
        ],
    )

    assert height >= 180
    assert 'th.sortable' in html
    assert 'addEventListener(\'click\'' in html
    assert 'width: 56px' in html
    assert 'aspect-ratio: 16 / 9' in html
    assert 'border-radius: 6px' in html
    assert 'width: 72px' in html
