from __future__ import annotations

import html


HERO_PORTRAIT_WIDTH_PX = 56
HERO_PORTRAIT_ASPECT_RATIO = "16 / 9"
HERO_PORTRAIT_BORDER_RADIUS_PX = 6
HERO_PORTRAIT_COLUMN_WIDTH_PX = 72
HERO_TABLE_ROW_HEIGHT_PX = 40


def hero_overview_fallback_headers(
    *,
    hero_matches_column: str,
    hero_wins_column: str,
    hero_losses_column: str,
) -> list[dict[str, object]]:
    return [
        {"label": "Icon", "type": "text", "sortable": False},
        {"label": "Hero", "type": "text", "sortable": True},
        {"label": hero_matches_column, "type": "number", "sortable": True},
        {"label": hero_wins_column, "type": "number", "sortable": True},
        {"label": hero_losses_column, "type": "number", "sortable": True},
        {"label": "WR", "type": "number", "sortable": True},
        {"label": "Avg K/D/A", "type": "text", "sortable": True},
        {"label": "KDA", "type": "number", "sortable": True},
        {"label": "Dur", "type": "number", "sortable": True},
        {"label": "NW", "type": "number", "sortable": True},
        {"label": "Dmg", "type": "number", "sortable": True},
        {"label": "Max K", "type": "number", "sortable": True},
        {"label": "Max Dmg", "type": "number", "sortable": True},
        {"label": "Rad WR", "type": "number", "sortable": True},
        {"label": "Dire WR", "type": "number", "sortable": True},
        {"label": "MVP", "type": "number", "sortable": True},
        {"label": "High", "type": "number", "sortable": True},
        {"label": "Tag", "type": "number", "sortable": True},
    ]


def matchup_fallback_headers() -> list[dict[str, object]]:
    return [
        {"label": "Icon", "type": "text", "sortable": False},
        {"label": "Hero", "type": "text", "sortable": True},
        {"label": "WR", "type": "number", "sortable": True},
        {"label": "Matches", "type": "number", "sortable": True},
        {"label": "Won", "type": "number", "sortable": True},
        {"label": "Lost", "type": "number", "sortable": True},
    ]


def build_hero_portrait_html(image_url: str, alt: str) -> str:
    return (
        '<div class="hero-portrait-wrap">'
        f'<img src="{html.escape(str(image_url))}" alt="{html.escape(str(alt))}"/>'
        "</div>"
    )


def build_sortable_html_table(
    *,
    table_id: str,
    headers: list[dict[str, object]],
    rows: list[list[dict[str, object]]],
) -> tuple[str, int]:
    header_html = "".join(
        (
            f'<th class="{"sortable" if bool(header.get("sortable")) else ""}" '
            f'data-type="{html.escape(str(header.get("type", "text")))}">'
            f"{html.escape(str(header['label']))}</th>"
        )
        for header in headers
    )
    row_html = []
    for row in rows:
        cell_html = []
        for cell in row:
            class_name = str(cell.get("class_name") or "")
            sort_value = html.escape(str(cell.get("sort_value") or ""))
            display_html = str(cell.get("display_html") or "")
            cell_html.append(f'<td class="{class_name}" data-sort="{sort_value}">{display_html}</td>')
        row_html.append(f"<tr>{''.join(cell_html)}</tr>")

    table_height = min(max(180, 52 + len(rows) * 42), 980)
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
        .fallback-table-wrap {{
          width: 100%;
          overflow-x: auto;
          border: 1px solid rgba(49, 51, 63, 0.2);
          border-radius: 0.5rem;
        }}
        .fallback-table {{
          width: 100%;
          border-collapse: collapse;
          font-size: 0.92rem;
        }}
        .fallback-table th,
        .fallback-table td {{
          padding: 0.45rem 0.55rem;
          border-bottom: 1px solid rgba(127, 127, 127, 0.14);
          white-space: nowrap;
          text-align: left;
          vertical-align: middle;
        }}
        .fallback-table th {{
          font-weight: 700;
          background: rgba(255, 255, 255, 0.04);
        }}
        .fallback-table th.sortable {{
          cursor: pointer;
          user-select: none;
        }}
        .fallback-table th.sortable:hover {{
          background: rgba(255, 255, 255, 0.08);
        }}
        .fallback-table td.num {{
          text-align: right;
        }}
        .fallback-table .hero-portrait-cell {{
          width: {HERO_PORTRAIT_COLUMN_WIDTH_PX}px;
          min-width: {HERO_PORTRAIT_COLUMN_WIDTH_PX}px;
        }}
        .fallback-table .hero-portrait-wrap {{
          display: flex;
          align-items: center;
          justify-content: center;
          width: {HERO_PORTRAIT_WIDTH_PX}px;
          aspect-ratio: {HERO_PORTRAIT_ASPECT_RATIO};
        }}
        .fallback-table .hero-portrait-wrap img {{
          display: block;
          width: {HERO_PORTRAIT_WIDTH_PX}px;
          height: 100%;
          object-fit: cover;
          border-radius: {HERO_PORTRAIT_BORDER_RADIUS_PX}px;
        }}
      </style>
    </head>
    <body>
      <div class="fallback-table-wrap">
        <table class="fallback-table" id="{html.escape(table_id)}">
          <thead><tr>{header_html}</tr></thead>
          <tbody>{''.join(row_html)}</tbody>
        </table>
      </div>
      <script>
        (() => {{
          const table = document.getElementById({table_id!r});
          if (!table) return;
          const tbody = table.querySelector('tbody');
          const headers = Array.from(table.querySelectorAll('th.sortable'));

          const compareValue = (raw, type) => {{
            if (type === 'number') {{
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
