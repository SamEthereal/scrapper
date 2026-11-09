"""Main CLI entry point for scraping, filtering, sorting, and searching opportunities."""

import argparse
import sys
from typing import List, Dict, Any

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


def render_opportunities_table(
    console: Console,
    items: List[Dict[str, Any]],
    title: str = "Opportunities",
) -> None:
    """Renders a formatted table of opportunities."""
    console.print(f"\n[bold green]{title}[/bold green] ([bold yellow]{len(items)}[/bold yellow] found)\n")

    if not items:
        console.print("[dim]No matching opportunities found.[/dim]\n")
        return

    table = Table(title=title, show_lines=True)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Title", style="bold white", width=34)
    table.add_column("Deadline", style="magenta", width=14)
    table.add_column("Portal / Apply Link", style="cyan", width=30)
    table.add_column("Highlights", style="green", width=32)

    for item in items:
        portal = item.get("official_portal") or item.get("apply_url") or "[dim]None[/dim]"
        highlights = item.get("key_highlights") or []
        hl_preview = "\n".join(f"• {h[:30]}..." if len(h) > 30 else f"• {h}" for h in highlights[:2])
        deadline_display = item.get("deadline_date") or item.get("deadline") or "[dim]N/A[/dim]"

        table.add_row(
            str(item["id"]),
            item["title"][:32] + ("..." if len(item["title"]) > 32 else ""),
            deadline_display,
            portal[:28] + ("..." if len(portal) > 28 else ""),
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
    table.add_column("Deadline", style="magenta", width=14)

    web_scraper = WebScraper()

    for item in parsed_items:
        type_badge = "[green]Opportunity[/green]" if item.is_opportunity else "[yellow]Promo/Ad[/yellow]"
        deadline_text = item.deadline_date or item.deadline or "[dim]N/A[/dim]"

        official_portal = None
        key_highlights = None

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


def build_parser() -> argparse.ArgumentParser:
    """Configures command-line arguments and subcommands."""
    parser = argparse.ArgumentParser(
        description="Opportunity Scraper, Database & Search Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # Command: scrape
    subparsers.add_parser("scrape", help="Fetch latest posts from Telegram & enrich with webpage details")

    # Command: search
    search_parser = subparsers.add_parser("search", help="Search opportunities by keyword")
    search_parser.add_argument("query", help="Keyword to search across titles and highlights")

    # Command: filter
    filter_parser = subparsers.add_parser("filter", help="Filter and sort opportunities")
    filter_parser.add_argument("--country", help="Filter by country (e.g. Spain, UK, USA)")
    filter_parser.add_argument("--level", help="Filter by level (e.g. PhD, Master, Undergraduate)")
    filter_parser.add_argument("--keyword", help="General keyword filter")
    filter_parser.add_argument(
        "--sort",
        choices=["deadline", "date", "title", "id"],
        default="date",
        help="Column to sort by (default: date)",
    )
    filter_parser.add_argument(
        "--order",
        choices=["asc", "desc"],
        default="desc",
        help="Sort direction (default: desc)",
    )
    filter_parser.add_argument(
        "--has-deadline",
        action="store_true",
        help="Only show opportunities with a specified deadline",
    )
    filter_parser.add_argument(
        "--open-only",
        action="store_true",
        help="Only show opportunities whose deadline has not passed",
    )

    # Command: list
    subparsers.add_parser("list", help="List all saved opportunities")

    # Command: closing-soon
    soon_parser = subparsers.add_parser("closing-soon", help="Show opportunities closing soon")
    soon_parser.add_argument("--days", type=int, default=60, help="Number of days window (default: 60)")

    return parser


def main():
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]Telegram & Web Opportunity Scraper & Search Engine[/bold cyan]\n"
            "[dim]Scrape, Persist, Deduplicate, Filter & Sort[/dim]",
            border_style="cyan",
        )
    )

    db = OpportunityDB()
    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand == "scrape":
        run_scraper(console, db)

    elif args.subcommand == "search":
        results = db.search(args.query)
        render_opportunities_table(console, results, title=f"Search Results for '{args.query}'")

    elif args.subcommand == "filter":
        results = db.filter_opportunities(
            keyword=args.keyword,
            country=args.country,
            level=args.level,
            open_only=args.open_only,
            has_deadline=args.has_deadline,
            sort_by=args.sort,
            order=args.order,
        )
        sort_info = f" (Sorted by {args.sort} {args.order.upper()})"
        render_opportunities_table(console, results, title=f"Filtered Opportunities{sort_info}")

    elif args.subcommand == "list":
        results = db.get_all(limit=50)
        render_opportunities_table(console, results, title="All Saved Opportunities")

    elif args.subcommand == "closing-soon":
        results = db.get_closing_soon(days=args.days)
        render_opportunities_table(
            console,
            results,
            title=f"Opportunities Closing Within Next {args.days} Days (Soonest First)",
        )

    else:
        # Default with no arguments: show usage and quick stats
        console.print(f"[bold cyan]Database Status:[/bold cyan] [green]{db.count()}[/green] opportunities stored.\n")
        console.print("[bold yellow]Available Commands:[/bold yellow]")
        console.print("  [cyan]uv run main.py scrape[/cyan]                      - Scrape & sync latest updates")
        console.print("  [cyan]uv run main.py list[/cyan]                        - List all stored opportunities")
        console.print("  [cyan]uv run main.py closing-soon[/cyan]                - Show opportunities closing in next 60 days")
        console.print("  [cyan]uv run main.py closing-soon --days 90[/cyan]      - Custom days window")
        console.print("  [cyan]uv run main.py search <keyword>[/cyan]            - Quick search (e.g. 'Spain')")
        console.print("  [cyan]uv run main.py filter --sort deadline --order asc[/cyan] - Show closing soonest")
        console.print("  [cyan]uv run main.py filter --country UK --level PhD[/cyan]   - Filter by country & level\n")


if __name__ == "__main__":
    main()
