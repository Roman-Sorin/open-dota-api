from __future__ import annotations

from rich.console import Console
from rich.table import Table

from models.dtos import ItemStat, ItemsResult, MatchRow, QueryFilters, StatsResult


class TerminalFormatter:
    def __init__(self) -> None:
        self.console = Console()

    def print_context(self, filters: QueryFilters, hero_name: str) -> None:
        period = f"last {filters.days} days" if filters.days else "all available"
        mode = filters.game_mode_name or "Any"

        self.console.print(f"[bold]Player:[/bold] {filters.player_id}")
        self.console.print(f"[bold]Hero:[/bold] {hero_name}")
        self.console.print(f"[bold]Mode:[/bold] {mode}")
        self.console.print(f"[bold]Period:[/bold] {period}")
        self.console.print()

    def print_stats(self, stats: StatsResult) -> None:
        self.console.print("[bold cyan]General Stats[/bold cyan]")
        self.console.print(f"Matches: {stats.matches}")
        self.console.print(f"Wins: {stats.wins}")
        self.console.print(f"Losses: {stats.losses}")
        self.console.print(f"Winrate: {stats.winrate:.2f}%")
        self.console.print()

        table = Table(title="Average Values", show_header=True, header_style="bold magenta")
        table.add_column("Kills", justify="right")
        table.add_column("Deaths", justify="right")
        table.add_column("Assists", justify="right")
        table.add_column("KDA", justify="right")
        table.add_column("Net Worth", justify="right")
        table.add_column("Damage", justify="right")
        table.add_row(
            f"{stats.avg_kills:.2f}",
            f"{stats.avg_deaths:.2f}",
            f"{stats.avg_assists:.2f}",
            f"{stats.kda_ratio:.2f}",
            f"{stats.avg_net_worth:,.0f}",
            f"{stats.avg_damage:,.0f}",
        )
        self.console.print(table)
        self.console.print()

        side_table = Table(title="Side Winrate", show_header=True, header_style="bold magenta")
        side_table.add_column("Radiant WR", justify="right")
        side_table.add_column("Dire WR", justify="right")
        side_table.add_row(f"{stats.radiant_wr:.2f}%", f"{stats.dire_wr:.2f}%")
        self.console.print(side_table)

    def print_items(self, items_result: ItemsResult) -> None:
        self.console.print("[bold cyan]Items[/bold cyan]")
        self.console.print(f"Matches analyzed: {items_result.total_matches}")

        self._print_item_table("Top Final Inventory Items", items_result.final_inventory_items)

        if items_result.purchased_items:
            self._print_item_table("Top Purchased Items", items_result.purchased_items)

        self.console.print(f"[yellow]{items_result.note}[/yellow]")

    def _print_item_table(self, title: str, rows: list[ItemStat]) -> None:
        table = Table(title=title, show_header=True, header_style="bold magenta")
        table.add_column("#", justify="right")
        table.add_column("Item")
        table.add_column("Matches", justify="right")
        table.add_column("Match %", justify="right")

        for idx, row in enumerate(rows, start=1):
            table.add_row(str(idx), row.item_name, str(row.count), f"{row.match_pct:.2f}%")

        self.console.print(table)

    def print_matches(self, rows: list[MatchRow]) -> None:
        self.console.print("[bold cyan]Recent Matches[/bold cyan]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("match_id")
        table.add_column("date")
        table.add_column("result")
        table.add_column("K/D/A")
        table.add_column("duration")
        table.add_column("net_worth", justify="right")
        table.add_column("items")

        for row in rows:
            table.add_row(
                str(row.match_id),
                row.started_at.strftime("%Y-%m-%d %H:%M"),
                row.result,
                row.kda,
                row.duration,
                f"{row.net_worth:,}" if row.net_worth is not None else "-",
                ", ".join(row.items[:4]) if row.items else "-",
            )

        self.console.print(table)

    def print_warning(self, message: str) -> None:
        self.console.print(f"[yellow]{message}[/yellow]")

    def print_error(self, message: str) -> None:
        self.console.print(f"[bold red]Error:[/bold red] {message}")

    def print_no_matches(self) -> None:
        self.print_warning("No matches found for provided filters.")
