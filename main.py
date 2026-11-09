"""Main CLI entry point for scraping, parsing, storing, and searching opportunities."""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from parsers.scholarship_parser import parse_post
from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
from storage.db import OpportunityDB

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def render_search_results(console: Console, term: str, db: OpportunityDB) -> None:
    """Displays search results from the database."""
    results = db.search(term)
    console.print(f"\n[bold green]Search Results for:[/bold green] '[bold yellow]{term}[/bold yellow]' ({len(results)} found)\n")

    if not results:
        console.print("[dim]No matching opportunities found.[/dim]\n")
        return

    table = Table(title=f"Matches for '{term}'", show_lines=True)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Title", style="bold white", width=36)
    table.add_column("Deadline", style="magenta", width=18)
    table.add_column("Official Portal", style="cyan")
    table.add_column("Highlights", style="green", width=30)

    for item in results:
        portal = item.get("official_portal") or item.get("apply_url") or "[dim]None[/dim]"
        highlights = item.get("key_highlights") or []
        hl_preview = "\n".join(f"• {h[:28]}..." if len(h) > 28 else f"• {h}" for h in highlights[:2])

        table.add_row(
            str(item["id"]),
            item["title"][:35] + ("..." if len(item["title"]) > 35 else ""),
            item.get("deadline") or "[dim]N/A[/dim]",
            portal[:35] + ("..." if len(portal) > 35 else ""),
            hl_preview or "[dim]None[/dim]",
        )

    console.print(table)


def run_scraper(console: Console, db: OpportunityDB) -> None:
    """Runs the scraping, enrichment, and storage pipeline."""
    channel_target = "https://t.me/OHUB4AllET"
    console.print(f"[yellow]1. Fetching recent posts from:[/yellow] [bold]{channel_target}[/bold]...\n")

    tg_scraper = TelegramScraper()
    try:
        raw_posts = tg_scraper.scrape_channel(channel_target, limit=6)
    except Exception as e:
        console.print(f"[bold red]⚠ Unable to reach Telegram preview ({channel_target}):[/bold red]")
        console.print(f"[dim]{e}[/dim]")
        console.print("[yellow]Notice: If your network or ISP restricts t.me, connecting via a VPN will resolve this.[/yellow]")
        console.print(f"[cyan]Current offline database still contains [bold green]{db.count()}[/bold green] saved opportunities.[/cyan]\n")
        return

    parsed_items = [parse_post(post) for post in raw_posts]

    table = Table(title="Scraped Feed & Database Sync Status", show_lines=True)
    table.add_column("Post ID", style="dim", width=8)
    table.add_column("Status", width=12)
    table.add_column("Type", width=12)
    table.add_column("Title", style="bold white", width=34)
    table.add_column("Deadline", style="magenta", width=18)

    web_scraper = WebScraper()

    for item in parsed_items:
        type_badge = "[green]Opportunity[/green]" if item.is_opportunity else "[yellow]Promo/Ad[/yellow]"
        deadline_text = item.deadline or "[dim]N/A[/dim]"

        official_portal = None
        key_highlights = None

        # If it's a specific opportunity with an article link, deep-scrape it
        has_specific_link = (
            item.is_opportunity
            and item.apply_url
            and not item.apply_url.rstrip("/").endswith("/opportunities")
        )

        if has_specific_link:
            try:
                page_data = web_scraper.scrape(item.apply_url)
                official_portal = page_data.apply_links[0] if page_data.apply_links else None
                key_highlights = page_data.key_highlights
            except Exception:
                pass

        # Save to database (deduplicates automatically)
        is_new = db.save_opportunity(
            item,
            official_portal=official_portal,
            key_highlights=key_highlights,
        )
        status_badge = "[bold green]✓ NEW[/bold green]" if is_new else "[dim]EXISTING[/dim]"

        table.add_row(
            item.post_id,
            status_badge,
            type_badge,
            item.title[:32] + ("..." if len(item.title) > 32 else ""),
            deadline_text,
        )

    console.print(table)
    console.print(f"\n[bold cyan]Total opportunities saved in DB:[/bold cyan] [bold green]{db.count()}[/bold green]\n")


def main():
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]Telegram & Web Opportunity Scraper & Search Engine[/bold cyan]\n"
            "[dim]Scrape, Persist, Deduplicate, and Query Opportunities[/dim]",
            border_style="cyan",
        )
    )

    db = OpportunityDB()

    # Check for CLI arguments: e.g. "uv run main.py search PhD"
    if len(sys.argv) > 2 and sys.argv[1].lower() == "search":
        search_query = " ".join(sys.argv[2:])
        render_search_results(console, search_query, db)
    elif len(sys.argv) == 2 and sys.argv[1].lower() == "list":
        render_search_results(console, "", db)
    else:
        # Run scraper and sync with DB
        run_scraper(console, db)
        console.print("[dim]Tip: You can search your saved database anytime with:[/dim]")
        console.print("  [cyan]uv run main.py search <keyword>[/cyan]  (e.g. [yellow]uv run main.py search Spain[/yellow])\n")


if __name__ == "__main__":
    main()
