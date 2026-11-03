"""Main CLI entry point for testing the scraper and parser."""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scrapers.telegram_scraper import TelegramScraper
from parsers.scholarship_parser import parse_post

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]Telegram & Web Opportunity Scraper[/bold cyan]\n"
            "[dim]Scraping & Parsing Real-world Opportunities[/dim]",
            border_style="cyan",
        )
    )

    channel_target = "https://t.me/OHUB4AllET"
    console.print(f"[yellow]Fetching recent posts from:[/yellow] [bold]{channel_target}[/bold]...\n")

    scraper = TelegramScraper()
    raw_posts = scraper.scrape_channel(channel_target, limit=6)

    # Parse each post using our parser function
    parsed_items = [parse_post(post) for post in raw_posts]

    # Render results in a rich table
    table = Table(title="Parsed Opportunities from @OHUB4AllET", show_lines=True)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Type", width=12)
    table.add_column("Title", style="bold white", width=36)
    table.add_column("Deadline", style="magenta", width=18)
    table.add_column("Apply Link", style="cyan")

    for item in parsed_items:
        type_badge = "[green]Opportunity[/green]" if item.is_opportunity else "[yellow]Promo/Ad[/yellow]"
        deadline_text = item.deadline or "[dim]N/A[/dim]"
        apply_link = item.apply_url or "[dim]No link[/dim]"

        table.add_row(
            item.post_id,
            type_badge,
            item.title[:35] + ("..." if len(item.title) > 35 else ""),
            deadline_text,
            apply_link,
        )

    console.print(table)


if __name__ == "__main__":
    main()
