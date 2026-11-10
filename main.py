"""Main CLI entry point for scraping, filtering, sorting, and searching opportunities & jobs."""

import argparse
import sys
from typing import List, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from parsers.scholarship_parser import parse_post
from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
from scrapers.job_scraper import JobScraper
from storage.db import OpportunityDB

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def render_opportunities_table(
    console: Console,
    items: List[Dict[str, Any]],
    title: str = "Opportunities",
) -> None:
    """Renders a formatted table of scholarship opportunities."""
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


def render_jobs_table(
    console: Console,
    jobs: List[Dict[str, Any]],
    title: str = "Job Listings",
) -> None:
    """Renders a formatted table of job listings."""
    console.print(f"\n[bold green]{title}[/bold green] ([bold yellow]{len(jobs)}[/bold yellow] found)\n")

    if not jobs:
        console.print("[dim]No matching jobs found.[/dim]\n")
        return

    table = Table(title=title, show_lines=True)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Job Title", style="bold white", width=32)
    table.add_column("Company", style="cyan", width=22)
    table.add_column("Location / Remote", style="magenta", width=24)
    table.add_column("Salary", style="green", width=18)
    table.add_column("Work-Life Score", style="yellow", width=16)

    for j in jobs:
        salary_text = j.get("salary") or "[dim]Not listed[/dim]"
        score = j.get("work_life_score")
        score_text = f"[bold green]{score}/100[/bold green]" if score else "[dim]N/A[/dim]"
        loc_display = j.get("location") or "Remote"

        table.add_row(
            str(j["id"]),
            j["title"][:30] + ("..." if len(j["title"]) > 30 else ""),
            j["company"][:20] + ("..." if len(j["company"]) > 20 else ""),
            loc_display[:22] + ("..." if len(loc_display) > 22 else ""),
            salary_text,
            score_text,
        )

    console.print(table)


def run_scholarship_scraper(console: Console, db: OpportunityDB) -> None:
    """Runs the scholarship scraping, enrichment, and storage pipeline."""
    channel_target = "https://t.me/OHUB4AllET"
    console.print(f"[yellow]1. Fetching recent scholarship posts from:[/yellow] [bold]{channel_target}[/bold]...\n")

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


def run_job_scraper(console: Console, db: OpportunityDB) -> None:
    """Scrapes remote jobs from 4dayweek.io and persists them to the database."""
    console.print("[yellow]Fetching remote jobs from:[/yellow] [bold]https://4dayweek.io/remote-jobs[/bold]...\n")

    scraper = JobScraper()
    try:
        jobs = scraper.scrape_4dayweek(limit=50)
    except Exception as e:
        console.print(f"[bold red]⚠ Error fetching jobs:[/bold red] {e}")
        return

    new_count = 0
    for job in jobs:
        is_new = db.save_job(job)
        if is_new:
            new_count += 1

    console.print(f"[bold green]✓ Scraped {len(jobs)} live jobs![/bold green] ([cyan]{new_count} new[/cyan], [dim]{len(jobs) - new_count} existing[/dim])")
    console.print(f"[bold cyan]Total jobs now in database:[/bold cyan] [bold green]{db.count_jobs()}[/bold green]\n")

    # Render top 10 scraped jobs
    recent_jobs = db.get_jobs(limit=10)
    render_jobs_table(console, recent_jobs, title="Recent 4-Day Remote Jobs")


def build_parser() -> argparse.ArgumentParser:
    """Configures command-line arguments and subcommands."""
    parser = argparse.ArgumentParser(
        description="Unified Opportunity & Job Scraper, Database & Search Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # ==========================
    # SCHOLARSHIPS COMMANDS
    # ==========================
    subparsers.add_parser("scrape", help="Fetch latest scholarship posts from Telegram & enrich with web portals")

    search_parser = subparsers.add_parser("search", help="Search scholarships by keyword")
    search_parser.add_argument("query", help="Keyword to search across titles and highlights")

    filter_parser = subparsers.add_parser("filter", help="Filter and sort scholarships")
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

    subparsers.add_parser("list", help="List all saved scholarships")

    soon_parser = subparsers.add_parser("closing-soon", help="Show scholarships closing soon")
    soon_parser.add_argument("--days", type=int, default=60, help="Number of days window (default: 60)")

    # ==========================
    # JOB BOARD COMMANDS (PHASE 2)
    # ==========================
    jobs_parser = subparsers.add_parser("jobs", help="Job board scraper & search (4dayweek.io)")
    job_sub = jobs_parser.add_subparsers(dest="job_action", help="Job operations")

    job_sub.add_parser("scrape", help="Scrape latest listings from 4dayweek.io into DB")
    job_sub.add_parser("list", help="List all saved job listings")

    j_search = job_sub.add_parser("search", help="Search jobs by keyword, title, or company")
    j_search.add_argument("query", help="Role, keyword, or company to search")

    j_filter = job_sub.add_parser("filter", help="Filter and sort jobs")
    j_filter.add_argument("--role", help="Filter by job role/title keyword")
    j_filter.add_argument("--company", help="Filter by company name")
    j_filter.add_argument("--salary", action="store_true", help="Only show jobs with listed salary")
    j_filter.add_argument("--remote", action="store_true", help="Only show remote jobs")
    j_filter.add_argument("--min-score", type=int, help="Minimum work-life score (0-100)")
    j_filter.add_argument(
        "--sort",
        choices=["score", "title", "company", "id"],
        default="id",
        help="Sort by field (default: id)",
    )
    j_filter.add_argument(
        "--order",
        choices=["asc", "desc"],
        default="desc",
        help="Sort direction (default: desc)",
    )

    # ==========================
    # WEB DASHBOARD (PHASE 3)
    # ==========================
    ui_parser = subparsers.add_parser("ui", help="Launch interactive web dashboard")
    ui_parser.add_argument("--port", type=int, default=8000, help="Port to run web dashboard (default: 8000)")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")

    return parser


def main():
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]Telegram & Web Opportunity & Job Search Engine[/bold cyan]\n"
            "[dim]Scholarships, Fellowships, Remote Work & 4-Day Jobs[/dim]",
            border_style="cyan",
        )
    )

    db = OpportunityDB()
    parser = build_parser()
    args = parser.parse_args()

    # Handle scholarships commands
    if args.subcommand == "scrape":
        run_scholarship_scraper(console, db)

    elif args.subcommand == "search":
        results = db.search(args.query)
        render_opportunities_table(console, results, title=f"Scholarship Results for '{args.query}'")

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
        render_opportunities_table(console, results, title=f"Filtered Scholarships{sort_info}")

    elif args.subcommand == "list":
        results = db.get_all(limit=50)
        render_opportunities_table(console, results, title="All Saved Scholarships")

    elif args.subcommand == "closing-soon":
        results = db.get_closing_soon(days=args.days)
        render_opportunities_table(
            console,
            results,
            title=f"Scholarships Closing Within Next {args.days} Days (Soonest First)",
        )

    # Handle jobs commands
    elif args.subcommand == "jobs":
        if args.job_action == "scrape":
            run_job_scraper(console, db)
        elif args.job_action == "search":
            results = db.search_jobs(args.query)
            render_jobs_table(console, results, title=f"Job Search Results for '{args.query}'")
        elif args.job_action == "filter":
            results = db.filter_jobs(
                keyword=args.role,
                company=args.company,
                has_salary=args.salary,
                remote_only=args.remote,
                min_score=args.min_score,
                sort_by=args.sort,
                order=args.order,
            )
            render_jobs_table(console, results, title="Filtered Job Listings")
        elif args.job_action == "list":
            results = db.get_jobs(limit=50)
            render_jobs_table(console, results, title="All Saved Job Listings")
        else:
            console.print("[yellow]Please specify a job command: scrape, list, search, or filter[/yellow]")
            console.print("  [cyan]uv run main.py jobs scrape[/cyan]           - Scrape live listings from 4dayweek.io")
            console.print("  [cyan]uv run main.py jobs list[/cyan]             - List all stored jobs")
            console.print("  [cyan]uv run main.py jobs search <role>[/cyan]     - Search by role or company (e.g. 'Design')")
            console.print("  [cyan]uv run main.py jobs filter --salary[/cyan]    - Only jobs with salary listed\n")

    # Handle web dashboard command
    elif args.subcommand == "ui":
        import uvicorn
        console.print(f"[bold green]Starting Web Dashboard at:[/bold green] [bold cyan]http://{args.host}:{args.port}[/bold cyan]")
        console.print("[dim]Press Ctrl+C to stop the server anytime.[/dim]\n")
        uvicorn.run("ui.app:app", host=args.host, port=args.port, reload=False)

    else:
        # Default with no arguments: show usage and stats
        console.print(f"[bold cyan]Database Status:[/bold cyan] [green]{db.count()}[/green] scholarships | [green]{db.count_jobs()}[/green] jobs stored.\n")
        console.print("[bold yellow]🎓 Scholarships Commands:[/bold yellow]")
        console.print("  [cyan]uv run main.py scrape[/cyan]                      - Scrape & sync latest updates")
        console.print("  [cyan]uv run main.py list[/cyan]                        - List all stored scholarships")
        console.print("  [cyan]uv run main.py closing-soon[/cyan]                - Show scholarships closing in next 60 days")
        console.print("  [cyan]uv run main.py filter --country Spain[/cyan]      - Filter scholarships by country")
        console.print("\n[bold yellow]💼 Work & Jobs Commands:[/bold yellow]")
        console.print("  [cyan]uv run main.py jobs scrape[/cyan]                 - Scrape 50 remote jobs from 4dayweek.io")
        console.print("  [cyan]uv run main.py jobs list[/cyan]                   - List all stored jobs")
        console.print("  [cyan]uv run main.py jobs search Design[/cyan]          - Search by role or skill")
        console.print("  [cyan]uv run main.py jobs filter --salary[/cyan]        - Only jobs with salary listed")
        console.print("  [cyan]uv run main.py jobs filter --min-score 90[/cyan]  - Only high work-life balance jobs")
        console.print("\n[bold yellow]🌐 Interactive Web Dashboard:[/bold yellow]")
        console.print("  [cyan]uv run main.py ui[/cyan]                          - Launch browser UI at http://127.0.0.1:8000\n")


if __name__ == "__main__":
    main()
