from webapp.fallback_tables import (
    build_table_fragment,
    build_shared_table_css,
    hero_overview_fallback_headers,
    matchup_fallback_headers,
)


def test_hero_overview_headers_use_shared_column_types() -> None:
    headers = hero_overview_fallback_headers(
        hero_matches_column="Matches",
        hero_wins_column="Won",
        hero_losses_column="Lost",
    )

    assert headers[0]["type"] == "icon"
    assert headers[1]["type"] == "hero"
    assert headers[5]["type"] == "percentage"
    assert headers[6]["type"] == "kda_text"
    assert headers[7]["type"] == "kda"
    assert headers[8]["type"] == "duration"
    assert headers[9]["type"] == "currency"
    assert headers[10]["type"] == "damage"


def test_matchup_headers_keep_fixed_column_order_and_types() -> None:
    headers = matchup_fallback_headers()

    assert [header["label"] for header in headers] == ["Icon", "Hero", "WR", "Matches", "Won", "Lost"]
    assert [header["type"] for header in headers] == ["icon", "hero", "percentage", "integer", "integer", "integer"]


def test_build_table_fragment_applies_column_classes() -> None:
    fragment = build_table_fragment(
        table_id="sample",
        headers=[{"label": "Hero", "type": "hero"}, {"label": "WR", "type": "percentage", "sortable": True}],
        body_html='<tr><td class="col-hero">Axe</td><td class="col-pct">55%</td></tr>',
    )

    assert 'class="col-hero"' in fragment
    assert 'class="col-pct sortable"' in fragment
    assert 'id="sample"' in fragment


def test_shared_table_css_defines_compact_numeric_and_icon_columns() -> None:
    css = build_shared_table_css(min_width_px=900)

    assert "min-width: min(100%, 900px)" in css
    assert "th.col-icon" in css
    assert "td.col-num" in css
    assert "td.col-pct" in css
