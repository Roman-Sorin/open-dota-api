from __future__ import annotations

import html


HERO_PORTRAIT_WIDTH_PX = 56
HERO_PORTRAIT_ASPECT_RATIO = "16 / 9"
HERO_PORTRAIT_BORDER_RADIUS_PX = 6
HERO_PORTRAIT_COLUMN_WIDTH_PX = 72
HERO_TABLE_ROW_HEIGHT_PX = 40
TABLE_CELL_PADDING = "0.5rem 0.65rem"
TABLE_FONT_SIZE = "0.84rem"
TABLE_HEADER_FONT_SIZE = "0.72rem"
TABLE_ROW_HEIGHT_PX = 42

COLUMN_TYPE_CLASS = {
    "icon": "col-icon",
    "hero": "col-hero",
    "item": "col-item",
    "text": "col-text",
    "result": "col-result",
    "integer": "col-num",
    "number": "col-num",
    "percentage": "col-pct",
    "duration": "col-duration",
    "kda_text": "col-kda-text",
    "kda": "col-kda",
    "currency": "col-currency",
    "damage": "col-damage",
    "items": "col-items",
    "tags": "col-tags",
    "action": "col-action",
    "datetime": "col-datetime",
    "status": "col-status",
}


def _column_class(column_type: str) -> str:
    return COLUMN_TYPE_CLASS.get(column_type, "col-text")


def hero_overview_fallback_headers(
    *,
    hero_matches_column: str,
    hero_wins_column: str,
    hero_losses_column: str,
) -> list[dict[str, object]]:
    return [
        {"label": "Icon", "type": "icon", "sortable": False},
        {"label": "Hero", "type": "hero", "sortable": True},
        {"label": hero_matches_column, "type": "integer", "sortable": True},
        {"label": hero_wins_column, "type": "integer", "sortable": True},
        {"label": hero_losses_column, "type": "integer", "sortable": True},
        {"label": "WR", "type": "percentage", "sortable": True},
        {"label": "Avg K/D/A", "type": "kda_text", "sortable": True},
        {"label": "KDA", "type": "kda", "sortable": True},
        {"label": "Dur", "type": "duration", "sortable": True},
        {"label": "NW", "type": "currency", "sortable": True},
        {"label": "Dmg", "type": "damage", "sortable": True},
        {"label": "Max K", "type": "integer", "sortable": True},
        {"label": "Max Dmg", "type": "damage", "sortable": True},
        {"label": "Rad WR", "type": "percentage", "sortable": True},
        {"label": "Dire WR", "type": "percentage", "sortable": True},
        {"label": "MVP", "type": "integer", "sortable": True},
        {"label": "High", "type": "integer", "sortable": True},
        {"label": "Tag", "type": "integer", "sortable": True},
    ]


def matchup_fallback_headers() -> list[dict[str, object]]:
    return [
        {"label": "Icon", "type": "icon", "sortable": False},
        {"label": "Hero", "type": "hero", "sortable": True},
        {"label": "WR", "type": "percentage", "sortable": True},
        {"label": "Matches", "type": "integer", "sortable": True},
        {"label": "Won", "type": "integer", "sortable": True},
        {"label": "Lost", "type": "integer", "sortable": True},
    ]


def build_hero_portrait_html(image_url: str, alt: str) -> str:
    return (
        '<div class="hero-portrait-wrap">'
        f'<img src="{html.escape(str(image_url))}" alt="{html.escape(str(alt))}"/>'
        "</div>"
    )


def build_shared_table_css(*, table_class: str = "shared-data-table", min_width_px: int = 760) -> str:
    return f"""
    :root {{
      --table-border-strong: rgba(49, 51, 63, 0.18);
      --table-border-soft: rgba(127, 127, 127, 0.12);
      --table-surface-header: rgba(255, 255, 255, 0.045);
      --table-surface-hover: rgba(148, 163, 184, 0.08);
      --table-text-muted: rgba(250, 250, 250, 0.72);
      --table-text-strong: rgba(250, 250, 250, 0.94);
    }}
    .table-shell {{
      width: 100%;
      overflow-x: auto;
      margin: 0.35rem 0 0.8rem 0;
      border: 1px solid var(--table-border-strong);
      border-radius: 0.55rem;
      background: rgba(15, 23, 42, 0.04);
    }}
    .{table_class} {{
      width: max-content;
      min-width: min(100%, {min_width_px}px);
      border-collapse: separate;
      border-spacing: 0;
      table-layout: auto;
      font-size: {TABLE_FONT_SIZE};
      color: var(--table-text-strong);
    }}
    .{table_class} thead th {{
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--table-surface-header);
      font-size: {TABLE_HEADER_FONT_SIZE};
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--table-text-muted);
      border-bottom: 1px solid var(--table-border-strong);
    }}
    .{table_class} th,
    .{table_class} td {{
      padding: {TABLE_CELL_PADDING};
      border-bottom: 1px solid var(--table-border-soft);
      white-space: nowrap;
      vertical-align: middle;
      height: {TABLE_ROW_HEIGHT_PX}px;
      box-sizing: border-box;
    }}
    .{table_class} tbody tr:hover td {{
      background: var(--table-surface-hover);
    }}
    .{table_class} th.sortable {{
      cursor: pointer;
      user-select: none;
    }}
    .{table_class} th.sortable:hover {{
      background: rgba(255, 255, 255, 0.08);
    }}
    .{table_class} th.col-icon,
    .{table_class} td.col-icon {{
      width: {HERO_PORTRAIT_COLUMN_WIDTH_PX}px;
      min-width: {HERO_PORTRAIT_COLUMN_WIDTH_PX}px;
      max-width: {HERO_PORTRAIT_COLUMN_WIDTH_PX}px;
      padding-right: 0.45rem;
      text-align: center;
    }}
    .{table_class} th.col-hero,
    .{table_class} td.col-hero,
    .{table_class} th.col-item,
    .{table_class} td.col-item,
    .{table_class} th.col-text,
    .{table_class} td.col-text,
    .{table_class} th.col-result,
    .{table_class} td.col-result,
    .{table_class} th.col-tags,
    .{table_class} td.col-tags,
    .{table_class} th.col-status,
    .{table_class} td.col-status {{
      text-align: left;
    }}
    .{table_class} th.col-num,
    .{table_class} td.col-num,
    .{table_class} th.col-pct,
    .{table_class} td.col-pct,
    .{table_class} th.col-duration,
    .{table_class} td.col-duration,
    .{table_class} th.col-kda,
    .{table_class} td.col-kda,
    .{table_class} th.col-currency,
    .{table_class} td.col-currency,
    .{table_class} th.col-damage,
    .{table_class} td.col-damage,
    .{table_class} th.col-datetime,
    .{table_class} td.col-datetime {{
      text-align: right;
    }}
    .{table_class} th.col-kda-text,
    .{table_class} td.col-kda-text {{
      text-align: center;
    }}
    .{table_class} th.col-action,
    .{table_class} td.col-action {{
      text-align: center;
    }}
    .{table_class} th.col-hero,
    .{table_class} td.col-hero {{
      min-width: 160px;
      max-width: 260px;
    }}
    .{table_class} th.col-item,
    .{table_class} td.col-item {{
      min-width: 220px;
      max-width: 320px;
    }}
    .{table_class} th.col-result,
    .{table_class} td.col-result {{
      min-width: 120px;
    }}
    .{table_class} th.col-items,
    .{table_class} td.col-items {{
      min-width: 240px;
      max-width: 420px;
      text-align: left;
    }}
    .{table_class} th.col-tags,
    .{table_class} td.col-tags {{
      min-width: 120px;
      max-width: 200px;
    }}
    .{table_class} th.col-status,
    .{table_class} td.col-status {{
      min-width: 100px;
    }}
    .{table_class} th.col-action,
    .{table_class} td.col-action {{
      width: 92px;
      min-width: 92px;
      max-width: 92px;
    }}
    .{table_class} th.col-num,
    .{table_class} td.col-num {{
      min-width: 72px;
    }}
    .{table_class} th.col-pct,
    .{table_class} td.col-pct {{
      min-width: 74px;
    }}
    .{table_class} th.col-duration,
    .{table_class} td.col-duration {{
      min-width: 82px;
    }}
    .{table_class} th.col-kda,
    .{table_class} td.col-kda {{
      min-width: 72px;
    }}
    .{table_class} th.col-kda-text,
    .{table_class} td.col-kda-text {{
      min-width: 108px;
    }}
    .{table_class} th.col-currency,
    .{table_class} td.col-currency,
    .{table_class} th.col-damage,
    .{table_class} td.col-damage {{
      min-width: 88px;
    }}
    .{table_class} th.col-datetime,
    .{table_class} td.col-datetime {{
      min-width: 156px;
    }}
    .{table_class} tbody tr:last-child td {{
      border-bottom: none;
    }}
    .{table_class} .hero-portrait-wrap {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: {HERO_PORTRAIT_WIDTH_PX}px;
      aspect-ratio: {HERO_PORTRAIT_ASPECT_RATIO};
      margin: 0 auto;
    }}
    .{table_class} .hero-portrait-wrap img {{
      display: block;
      width: {HERO_PORTRAIT_WIDTH_PX}px;
      height: 100%;
      object-fit: cover;
      border-radius: {HERO_PORTRAIT_BORDER_RADIUS_PX}px;
    }}
    """


def build_table_fragment(
    *,
    table_id: str,
    headers: list[dict[str, object]],
    body_html: str,
    table_class: str = "shared-data-table",
) -> str:
    header_html = "".join(
        (
            f'<th class="{_build_header_class(header)}" '
            f'data-type="{html.escape(str(header.get("type", "text")))}">'
            f"{html.escape(str(header['label']))}</th>"
        )
        for header in headers
    )
    return (
        '<div class="table-shell">'
        f'<table class="{html.escape(table_class)}" id="{html.escape(table_id)}">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table></div>"
    )


def build_sortable_html_table(
    *,
    table_id: str,
    headers: list[dict[str, object]],
    rows: list[list[dict[str, object]]],
    min_width_px: int = 760,
) -> tuple[str, int]:
    row_html: list[str] = []
    for row in rows:
        cell_html = []
        for cell in row:
            cell_class = _build_cell_class(cell)
            sort_value = html.escape(str(cell.get("sort_value") or ""))
            display_html = str(cell.get("display_html") or "")
            cell_html.append(f'<td class="{cell_class}" data-sort="{sort_value}">{display_html}</td>')
        row_html.append(f"<tr>{''.join(cell_html)}</tr>")

    table_height = min(max(200, 60 + len(rows) * TABLE_ROW_HEIGHT_PX), 980)
    table_html = f"""
    <html>
    <head>
      <meta charset="utf-8" />
      <style>
        html, body {{
          margin: 0;
          padding: 0;
          background: transparent;
          color: rgba(250, 250, 250, 0.92);
          font-family: sans-serif;
        }}
        {build_shared_table_css(min_width_px=min_width_px)}
      </style>
    </head>
    <body>
      {build_table_fragment(table_id=table_id, headers=headers, body_html=''.join(row_html))}
      <script>
        (() => {{
          const table = document.getElementById({table_id!r});
          if (!table) return;
          const tbody = table.querySelector('tbody');
          const headers = Array.from(table.querySelectorAll('th.sortable'));

          const compareValue = (raw, type) => {{
            if (['integer', 'number', 'percentage', 'duration', 'kda', 'currency', 'damage', 'datetime'].includes(type)) {{
              const numeric = Number(raw);
              return Number.isNaN(numeric) ? Number.NEGATIVE_INFINITY : numeric;
            }}
            return String(raw || '').toLowerCase();
          }};

          headers.forEach((header) => {{
            header.addEventListener('click', () => {{
              const columnIndex = Array.from(header.parentElement.children).indexOf(header);
              const type = header.dataset.type || 'text';
              const currentOrder = header.dataset.order === 'asc' ? 'asc' : 'desc';
              const nextOrder = currentOrder === 'asc' ? 'desc' : 'asc';
              headers.forEach((other) => {{ other.dataset.order = ''; }});
              header.dataset.order = nextOrder;

              const rows = Array.from(tbody.querySelectorAll('tr'));
              rows.sort((left, right) => {{
                const leftCell = left.children[columnIndex];
                const rightCell = right.children[columnIndex];
                const leftValue = compareValue(leftCell.dataset.sort ?? leftCell.textContent, type);
                const rightValue = compareValue(rightCell.dataset.sort ?? rightCell.textContent, type);
                if (leftValue < rightValue) return nextOrder === 'asc' ? -1 : 1;
                if (leftValue > rightValue) return nextOrder === 'asc' ? 1 : -1;
                return 0;
              }});

              rows.forEach((row) => tbody.appendChild(row));
            }});
          }});
        }})();
      </script>
    </body>
    </html>
    """
    return table_html, table_height


def _build_header_class(header: dict[str, object]) -> str:
    column_type = str(header.get("type", "text"))
    class_names = [_column_class(column_type)]
    if bool(header.get("sortable")):
        class_names.append("sortable")
    extra_class = str(header.get("class_name") or "").strip()
    if extra_class:
        class_names.append(extra_class)
    return " ".join(class_names)


def _build_cell_class(cell: dict[str, object]) -> str:
    class_names: list[str] = []
    column_type = str(cell.get("type", "")).strip()
    if column_type:
        class_names.append(_column_class(column_type))
    legacy_class = str(cell.get("class_name") or "").strip()
    if legacy_class:
        class_names.extend(part for part in legacy_class.split() if part)
    return " ".join(class_names)
