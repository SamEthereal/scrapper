"""Main CLI entry point for testing the scraper and parser."""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
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
    console.print(f"[yellow]1. Fetching recent posts from:[/yellow] [bold]{channel_target}[/bold]...\n")

    tg_scraper = TelegramScraper()
    raw_posts = tg_scraper.scrape_channel(channel_target, limit=6)

    # Parse each post using our parser function
    parsed_items = [parse_post(post) for post in raw_posts]

    # Render Telegram overview table
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

    # 2. Deep scrape the first real opportunity web page (ignoring generic root pages)
    specific_opps = [
        it for it in parsed_items
        if it.is_opportunity and it.apply_url and not it.apply_url.rstrip("/").endswith("/opportunities")
    ]
    if specific_opps:
        target_opp = specific_opps[0]
        console.print(f"\n[bold yellow]2. Deep Scraping Web Page for Post #{target_opp.post_id}:[/bold yellow]")
        console.print(f"[dim]{target_opp.apply_url}[/dim]\n")

        web_scraper = WebScraper()
        try:
            web_data = web_scraper.scrape(target_opp.apply_url)

            # Display Highlights
            highlights_text = "\n".join(f" • [green]✓[/green] {h}" for h in web_data.key_highlights)
            if not highlights_text:
                highlights_text = "[dim]No highlights extracted[/dim]"

            # Display Official Portals
            portals_text = "\n".join(f" • [cyan]{link}[/cyan]" for link in web_data.apply_links[:3])
            if not portals_text:
                portals_text = "[dim]No direct application links found[/dim]"

            details_panel = Panel(
                f"[bold white]{web_data.title}[/bold white]\n\n"
                f"[bold magenta]Key Highlights & Benefits:[/bold magenta]\n{highlights_text}\n\n"
                f"[bold magenta]Official Application Portals:[/bold magenta]\n{portals_text}",
                title="[bold green]Enriched Webpage Data[/bold green]",
                border_style="green",
            )
            console.print(details_panel)

        except Exception as e:
            console.print(f"[red]Failed to scrape webpage: {e}[/red]")


if __name__ == "__main__":
    main()
