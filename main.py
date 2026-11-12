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
from scrapers.wwr_scraper import WWRScraper
from scrapers.grant_scraper import GrantScraper
from storage.db import OpportunityDB
from services.matcher import ProfileMatcher
from services.copilot import ApplicationCopilot

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


def render_profile_card(console: Console, profile: Dict[str, Any]) -> None:
    """Renders user profile details in a formatted rich Panel."""
    skills_badges = "  ".join(f"[bold cyan]• {s}[/bold cyan]" for s in profile.get("skills_list", []))
    roles_badges = "  ".join(f"[bold green]• {r}[/bold green]" for r in profile.get("target_roles_list", []))

    content = (
        f"[bold white text-lg]{profile.get('full_name')}[/bold white text-lg]  "
        f"[dim]({profile.get('email') or 'No email set'})[/dim]\n"
        f"[bold yellow]{profile.get('title')}[/bold yellow]\n\n"
        f"[bold]🎓 Degree:[/bold] {profile.get('degree')}  |  "
        f"[bold]⏳ Experience:[/bold] {profile.get('experience_years')} yrs  |  "
        f"[bold]📍 Preferred Locations:[/bold] {profile.get('preferred_locations')}\n\n"
        f"[bold]🎯 Target Roles:[/bold]\n{roles_badges or '[dim]None specified[/dim]'}\n\n"
        f"[bold]⚡ Key Skills & Tools:[/bold]\n{skills_badges or '[dim]None specified[/dim]'}\n\n"
        f"[bold]📝 Bio / Summary:[/bold]\n[dim]{profile.get('bio')}[/dim]"
    )
    console.print(Panel(content, title="[bold green]Candidate AI Profile (Active)[/bold green]", border_style="green"))


def render_matched_table(
    console: Console,
    items: List[Dict[str, Any]],
    item_type: str = "job",
    title: str = "Ranked AI Matches",
) -> None:
    """Renders opportunities or jobs ranked by AI Match Score."""
    console.print(f"\n[bold green]{title}[/bold green] ([bold yellow]{len(items)}[/bold yellow] evaluated)\n")
    if not items:
        console.print("[dim]No listings found to rank.[/dim]\n")
        return

    table = Table(title=title, show_lines=True)
    table.add_column("Score", style="bold", width=9)
    table.add_column("Verdict", style="dim", width=17)
    table.add_column("Title / Role", style="bold white", width=30)
    table.add_column("Entity / Host", style="cyan", width=20)
    table.add_column("Matched Skills", style="green", width=22)
    table.add_column("Key Match Justification", style="yellow", width=34)

    for it in items:
        match = it.get("match", {})
        score = match.get("score", 0)
        grade = match.get("grade", "N/A")
        color = match.get("color", "white")
        matched = ", ".join(match.get("matched_skills", [])[:3]) or "Domain fit"
        reasons = match.get("reasons", [])
        reason_txt = reasons[0] if reasons else "Profile aligns"

        score_badge = f"[{color}]{score}%[/{color}]"
        name_col = it.get("company") if item_type == "job" else (it.get("official_portal") or "Telegram")

        table.add_row(
            score_badge,
            f"[{color}]{grade}[/{color}]",
            it["title"][:28] + ("..." if len(it["title"]) > 28 else ""),
            (name_col or "")[:18],
            matched[:20] + ("..." if len(matched) > 20 else ""),
            reason_txt[:32] + ("..." if len(reason_txt) > 32 else ""),
        )

    console.print(table)


def render_grants_table(
    console: Console,
    grants: List[Dict[str, Any]],
    title: str = "Tech Grants & Startup Accelerators",
) -> None:
    """Renders formatted table of Tech Grants & Accelerators."""
    console.print(f"\n[bold green]{title}[/bold green] ([bold yellow]{len(grants)}[/bold yellow] programs)\n")
    if not grants:
        console.print("[dim]No grant opportunities recorded yet. Run 'uv run main.py grants scrape' to index.[/dim]\n")
        return

    table = Table(title=title, show_lines=True)
    table.add_column("ID", style="dim", width=5)
    table.add_column("Program / Grant Name", style="bold white", width=34)
    table.add_column("Organization", style="cyan", width=22)
    table.add_column("Capital / Funding", style="green", width=26)
    table.add_column("Stage", style="magenta", width=22)
    table.add_column("Deadline", style="yellow", width=16)

    for g in grants:
        table.add_row(
            str(g["id"]),
            g["title"][:32] + ("..." if len(g["title"]) > 32 else ""),
            g["organization"][:20] + ("..." if len(g["organization"]) > 20 else ""),
            (g.get("funding_amount") or "N/A")[:24],
            (g.get("stage") or "Pre-Seed")[:20],
            (g.get("deadline_date") or g.get("deadline") or "Rolling")[:14],
        )

    console.print(table)


def render_sources_table(console: Console, db: OpportunityDB) -> None:
    """Renders real-time status and metrics of all configured scraping engines."""
    all_jobs = db.get_jobs(limit=1000)
    wwr_count = sum(1 for j in all_jobs if j.get("source") == "WeWorkRemotely")
    day4_count = sum(1 for j in all_jobs if j.get("source") == "4dayweek.io")

    console.print("\n[bold cyan]Multi-Vertical Scraping Engines & Radar Status[/bold cyan]\n")

    table = Table(title="Scraper Engines Health & Metrics", show_lines=True)
    table.add_column("Engine", style="bold white", width=26)
    table.add_column("Target Source", style="cyan", width=32)
    table.add_column("Category", style="yellow", width=24)
    table.add_column("Indexed Items", style="green", justify="right", width=14)
    table.add_column("Status", width=14)

    engines = [
        ("Telegram Channel Preview", "https://t.me/OHUB4AllET", "Scholarships & Fellowships", db.count(), "[bold green]● Active[/bold green]"),
        ("4-Day Week Job Cards", "https://4dayweek.io/remote-jobs", "Work-Life Remote Jobs", day4_count, "[bold green]● Active[/bold green]"),
        ("WeWorkRemotely RSS", "https://weworkremotely.com/...rss", "Remote Tech & Gigs", wwr_count, "[bold green]● Active[/bold green]"),
        ("Tech Grants & Accelerators", "YC, Techstars, Mozilla, EU", "Grants & Venture Capital", db.count_grants(), "[bold green]● Active[/bold green]"),
    ]

    for name, target, cat, count, status in engines:
        table.add_row(name, target, cat, str(count), status)

    console.print(table)


def run_wwr_scraper(console: Console, db: OpportunityDB) -> None:
    """Executes WeWorkRemotely RSS scraping cycle and stores new jobs."""
    console.print("[yellow]Ingesting remote tech jobs & developer gigs from WeWorkRemotely...[/yellow]\n")
    scraper = WWRScraper()
    jobs = scraper.scrape(limit=50)
    new_count = sum(1 for j in jobs if db.save_job(j))
    console.print(f"[bold green]✓ Scraped {len(jobs)} live WWR jobs![/bold green] ([cyan]{new_count} newly indexed[/cyan], [dim]{len(jobs)-new_count} existing[/dim])")
    console.print(f"[bold cyan]Total jobs now in database:[/bold cyan] [bold yellow]{db.count_jobs()}[/bold yellow]\n")


def run_grant_scraper(console: Console, db: OpportunityDB) -> None:
    """Executes Tech Grants & Startup Accelerators indexing cycle."""
    console.print("[yellow]Indexing premier Tech Grants, Startup Accelerators & AI Compute credits...[/yellow]\n")
    scraper = GrantScraper()
    grants = scraper.scrape(limit=30)
    new_count = sum(1 for g in grants if db.save_grant(g))
    console.print(f"[bold green]✓ Indexed {len(grants)} grant & accelerator programs![/bold green] ([cyan]{new_count} new[/cyan])")
    console.print(f"[bold cyan]Total grants in database:[/bold cyan] [bold yellow]{db.count_grants()}[/bold yellow]\n")


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

    # ==========================
    # BACKGROUND SCHEDULER
    # ==========================
    auto_parser = subparsers.add_parser("auto", help="Run automated background scraping cycles")
    auto_parser.add_argument("--interval", type=int, default=60, help="Minutes between scrape cycles (default: 60)")
    auto_parser.add_argument("--once", action="store_true", help="Run a single cycle and exit (useful for cron/task schedulers)")

    # ==========================
    # MILESTONE 11: USER PROFILE
    # ==========================
    prof_parser = subparsers.add_parser("profile", help="Manage candidate profile for AI matching")
    prof_sub = prof_parser.add_subparsers(dest="profile_action", help="Profile operations")
    prof_sub.add_parser("view", help="View current candidate profile")
    p_set = prof_sub.add_parser("set", help="Update candidate profile")
    p_set.add_argument("--name", help="Full name")
    p_set.add_argument("--email", help="Contact email")
    p_set.add_argument("--title", help="Current or target headline")
    p_set.add_argument("--skills", help="Comma-separated skills (e.g. 'Python, FastAPI, Docker')")
    p_set.add_argument("--degree", help="Highest educational degree")
    p_set.add_argument("--exp", type=int, help="Years of professional experience")
    p_set.add_argument("--locations", help="Preferred work locations / Remote")
    p_set.add_argument("--roles", help="Comma-separated target roles")
    p_set.add_argument("--bio", help="Professional summary or bio")

    # ==========================
    # MILESTONE 11: AI MATCHING
    # ==========================
    match_parser = subparsers.add_parser("match", help="Rank jobs or scholarships by AI Profile Fit Score")
    match_sub = match_parser.add_subparsers(dest="match_target", help="Listing type to match")
    m_jobs = match_sub.add_parser("jobs", help="Rank jobs by profile match score")
    m_jobs.add_argument("--min-score", type=int, default=0, help="Minimum fit score (0-100)")
    m_opps = match_sub.add_parser("opps", help="Rank scholarships by profile match score")
    m_opps.add_argument("--min-score", type=int, default=0, help="Minimum fit score (0-100)")

    # ==========================
    # MILESTONE 11: 1-CLICK COPILOT
    # ==========================
    copilot_parser = subparsers.add_parser("copilot", help="Generate tailored Cover Letters, Pitch Decks or Statements of Purpose")
    copilot_parser.add_argument("--type", choices=["job", "opp", "grant"], required=True, help="Type of listing (job, opp, or grant)")
    copilot_parser.add_argument("--id", type=int, required=True, help="Database ID of the listing")
    copilot_parser.add_argument("--tone", choices=["professional", "academic"], default="professional", help="Document tone")
    copilot_parser.add_argument("--save", action="store_true", help="Save output to a markdown file")

    # ==========================
    # MILESTONE 12: WEWORKREMOTELY GIGS
    # ==========================
    wwr_parser = subparsers.add_parser("wwr", help="WeWorkRemotely remote developer jobs & gigs")
    wwr_sub = wwr_parser.add_subparsers(dest="wwr_action", help="WWR operations")
    wwr_sub.add_parser("scrape", help="Scrape latest developer jobs from WeWorkRemotely RSS")

    # ==========================
    # MILESTONE 12: TECH GRANTS & ACCELERATORS
    # ==========================
    grant_parser = subparsers.add_parser("grants", help="Tech Grants, Accelerators & Venture Funds")
    grant_sub = grant_parser.add_subparsers(dest="grant_action", help="Grant operations")
    grant_sub.add_parser("scrape", help="Index premier Tech Grants & Accelerators")
    grant_sub.add_parser("list", help="List all stored Tech Grants & Accelerators")
    g_search = grant_sub.add_parser("search", help="Search grants by keyword or entity")
    g_search.add_argument("query", help="Keyword or organization to search")

    # ==========================
    # MILESTONE 12: MULTI-VERTICAL RADAR SOURCES
    # ==========================
    subparsers.add_parser("sources", help="Display all active scraping engines, metrics & health")

    # ==========================
    # MILESTONE 13: TELEGRAM ALERT DISPATCHER
    # ==========================
    notify_parser = subparsers.add_parser("notify", help="Telegram Alert Dispatcher commands")
    notify_parser.add_argument("--test", action="store_true", help="Send a test verification notification to connected Telegram")
    notify_parser.add_argument("--detect", action="store_true", help="Auto-detect chat ID from recent bot messages")
    notify_parser.add_argument("--type", choices=["job", "opp", "grant"], help="Type of item to send")
    notify_parser.add_argument("--id", type=int, help="Database ID of item to send")

    # ==========================
    # MILESTONE 15: AI RESUME & DYNAMIC RECOMMENDATIONS
    # ==========================
    resume_parser = subparsers.add_parser("resume", help="AI Resume parsing, grade extraction & dynamic recommendations")
    resume_sub = resume_parser.add_subparsers(dest="resume_action", help="Resume operations")
    r_parse = resume_sub.add_parser("parse", help="Parse resume file (.pdf, .txt, .md) and extract credentials/grades")
    r_parse.add_argument("file", help="Path to resume file (.pdf, .txt, .md)")
    r_parse.add_argument("--save", action="store_true", help="Sync extracted credentials directly into active user profile")
    resume_sub.add_parser("recs", help="Generate dynamic recommendations based on candidate's calibrated resume profile")

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

    # Handle background automation command
    elif args.subcommand == "auto":
        from services.scheduler import ScraperScheduler
        scheduler = ScraperScheduler(db)
        if args.once:
            scheduler.run_cycle()
        else:
            scheduler.start(interval_minutes=args.interval)

    # Handle candidate profile commands (Milestone 11)
    elif args.subcommand == "profile":
        if args.profile_action == "set":
            current = db.get_user_profile()
            updated = db.save_user_profile(
                full_name=args.name or current["full_name"],
                email=args.email if args.email is not None else current["email"],
                title=args.title if args.title is not None else current["title"],
                skills=args.skills if args.skills is not None else current["skills"],
                degree=args.degree if args.degree is not None else current["degree"],
                experience_years=args.exp if args.exp is not None else current["experience_years"],
                preferred_locations=args.locations if args.locations is not None else current["preferred_locations"],
                target_roles=args.roles if args.roles is not None else current["target_roles"],
                bio=args.bio if args.bio is not None else current["bio"],
            )
            console.print("[bold green]✓ Candidate profile updated successfully![/bold green]\n")
            render_profile_card(console, updated)
        else:
            profile = db.get_user_profile()
            render_profile_card(console, profile)

    # Handle AI match ranking commands (Milestone 11)
    elif args.subcommand == "match":
        profile = db.get_user_profile()
        if args.match_target == "opps":
            items = db.get_all(limit=50)
            enriched = ProfileMatcher.enrich_items(profile, items, item_type="opportunity")
            if args.min_score > 0:
                enriched = [x for x in enriched if x.get("match", {}).get("score", 0) >= args.min_score]
            enriched.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=True)
            render_matched_table(console, enriched, item_type="opp", title="Scholarships Ranked by AI Match Score")
        else:
            items = db.get_jobs(limit=50)
            enriched = ProfileMatcher.enrich_items(profile, items, item_type="job")
            if args.min_score > 0:
                enriched = [x for x in enriched if x.get("match", {}).get("score", 0) >= args.min_score]
            enriched.sort(key=lambda x: x.get("match", {}).get("score", 0), reverse=True)
            render_matched_table(console, enriched, item_type="job", title="Jobs Ranked by AI Match Score")

    # Handle 1-Click Application Copilot (Milestone 11)
    elif args.subcommand == "copilot":
        profile = db.get_user_profile()
        item_type = "job" if args.type == "job" else ("grant" if args.type == "grant" else "opportunity")
        if args.type == "job":
            item = db.get_job_by_id(args.id)
        elif args.type == "grant":
            item = db.get_grant_by_id(args.id)
        else:
            item = db.get_opportunity_by_id(args.id)

        if not item:
            console.print(f"[bold red]Listing not found for ID {args.id} (type: {args.type})[/bold red]")
            return

        doc = ApplicationCopilot.generate_document(
            profile=profile,
            item=item,
            item_type=item_type,
            tone=args.tone,
        )

        console.print(f"\n[bold green]✨ AI Application Copilot Generated:[/bold green] [bold white]{doc['title']}[/bold white]\n")
        console.print(Panel(doc["markdown"], title=f"[bold cyan]{doc['title']}[/bold cyan]", border_style="cyan"))

        if args.save:
            from pathlib import Path
            clean_name = f"application_{args.type}_{args.id}.md"
            Path(clean_name).write_text(doc["markdown"], encoding="utf-8")
            console.print(f"\n[bold green]✓ Document saved to disk:[/bold green] [cyan]{clean_name}[/cyan]\n")

    # Handle WeWorkRemotely developer jobs & gigs (Milestone 12)
    elif args.subcommand == "wwr":
        if args.wwr_action == "scrape":
            run_wwr_scraper(console, db)
        else:
            console.print("[yellow]Usage: uv run main.py wwr scrape[/yellow]")

    # Handle Tech Grants & Accelerators (Milestone 12)
    elif args.subcommand == "grants":
        if args.grant_action == "scrape":
            run_grant_scraper(console, db)
        elif args.grant_action == "search":
            results = db.get_grants(keyword=args.query)
            render_grants_table(console, results, title=f"Tech Grants Search Results for '{args.query}'")
        elif args.grant_action == "list":
            results = db.get_grants(limit=50)
            render_grants_table(console, results, title="All Indexed Tech Grants & Accelerators")
        else:
            console.print("[yellow]Please specify a grant command: scrape, list, or search[/yellow]")
            console.print("  [cyan]uv run main.py grants scrape[/cyan]          - Index premier grants & accelerators")
            console.print("  [cyan]uv run main.py grants list[/cyan]            - List all stored grants")
            console.print("  [cyan]uv run main.py grants search <keyword>[/cyan] - Search grants by keyword or entity\n")

    # Handle Multi-Vertical Sources status (Milestone 12)
    elif args.subcommand == "sources":
        render_sources_table(console, db)

    # Handle Telegram Notifications (Milestone 13)
    elif args.subcommand == "notify":
        from services.telegram_bot import TelegramAlertDispatcher
        bot = TelegramAlertDispatcher(db)

        if args.detect:
            console.print("[yellow]Querying Telegram for incoming user messages...[/yellow]")
            res = bot.detect_chat_id()
            if res.get("success"):
                console.print(f"[bold green]✓ Linked Chat:[/bold green] {res.get('user')} (ID: [bold cyan]{res.get('chat_id')}[/bold cyan])")
            elif res.get("waiting"):
                console.print(f"[bold yellow]⏳ Awaiting Interaction:[/bold yellow] {res.get('message')}")
            else:
                console.print(f"[bold red]⚠ Error:[/bold red] {res.get('error')}")

        elif args.test:
            console.print("[yellow]Sending verification test message to phone...[/yellow]")
            res = bot.test_connection()
            if res.get("success"):
                console.print("[bold green]✓ Test alert delivered successfully to Telegram![/bold green]")
            else:
                console.print(f"[bold red]⚠ Dispatch failed:[/bold red] {res.get('error')}")

        elif args.id and args.type:
            item_type = "job" if args.type == "job" else ("grant" if args.type == "grant" else "opportunity")
            if item_type == "job":
                item = db.get_job_by_id(args.id)
            elif item_type == "grant":
                item = db.get_grant_by_id(args.id)
            else:
                item = db.get_opportunity_by_id(args.id)

            if not item:
                console.print(f"[bold red]⚠ Item {args.type} #{args.id} not found in database.[/bold red]")
                return

            profile = db.get_user_profile()
            match = ProfileMatcher.match_item(profile, item, item_type=item_type)
            res = bot.send_opportunity_card(item, item_type=item_type, match=match)
            if res.get("success"):
                console.print(f"[bold green]✓ Dispatched {item_type} #{args.id} to Telegram successfully![/bold green]")
            else:
                console.print(f"[bold red]⚠ Failed to send:[/bold red] {res.get('error') or res.get('message')}")
        else:
            info = bot.get_bot_info()
            console.print(f"[bold cyan]Telegram Bot Status:[/bold cyan] {info}")

    # Handle AI Resume & Recommendations (Milestone 15)
    elif args.subcommand == "resume":
        from services.ai_resume import AIResumeService
        if args.resume_action == "parse":
            from pathlib import Path
            p = Path(args.file)
            if not p.exists():
                console.print(f"[bold red]File not found: {args.file}[/bold red]")
                return
            file_bytes = p.read_bytes()
            text = AIResumeService.extract_text(file_bytes, p.name)
            parsed = AIResumeService.parse_resume(text)

            console.print(f"\n[bold green]✨ AI Resume Parsed Successfully ({parsed.get('parser_used', 'Free AI')}):[/bold green]\n")
            table = Table(title="Extracted Candidate Credentials", show_lines=True)
            table.add_column("Field", style="bold cyan", width=24)
            table.add_column("Extracted Value", style="white", width=55)
            table.add_row("Full Name", parsed.get("full_name") or "Applicant")
            table.add_row("Academic Standing / GPA", f"[bold yellow]{parsed.get('gpa_grades') or 'N/A'}[/bold yellow]")
            table.add_row("Degree & Field", parsed.get("degree") or "N/A")
            table.add_row("Experience Standing", f"{parsed.get('experience_years', 0)}+ Years ({parsed.get('title') or 'Specialist'})")
            table.add_row("Core Competencies", parsed.get("skills") or "N/A")
            table.add_row("Target Roles", parsed.get("target_roles") or "N/A")
            table.add_row("Executive Bio", parsed.get("bio") or "N/A")
            console.print(table)

            if args.save:
                db.update_resume_data(resume_raw=text, extracted=parsed)
                console.print("\n[bold green]✓ Synced extracted credentials to user profile & recalibrated platform![/bold green]\n")
            else:
                console.print("\n[dim]To sync to your profile: add --save[/dim]\n")

        elif args.resume_action == "recs":
            from services.ai_resume import AIResumeService
            profile = db.get_user_profile()
            recs = AIResumeService.get_dynamic_recommendations(profile, db)
            console.print(f"\n[bold green]🎯 Tailored Dynamic AI Recommendations:[/bold green]\n")
            console.print(Panel(recs["summary"], title="[bold cyan]AI Strategic Guidance[/bold cyan]", border_style="cyan"))

            if recs.get("scholarships"):
                console.print("\n[bold yellow]🎓 Top Matching Scholarships (Academic Merit Focus):[/bold yellow]")
                for o in recs["scholarships"]:
                    m = o.get("match", {})
                    reason = m.get("reasons", [""])[0]
                    console.print(f"  • [bold white]{o['title']}[/bold white] — [bold green]{m.get('score')}% Match[/bold green]")
                    console.print(f"    [dim]{reason}[/dim]")

            if recs.get("jobs"):
                console.print("\n[bold yellow]💼 Top Matching 4-Day Remote Jobs:[/bold yellow]")
                for j in recs["jobs"]:
                    m = j.get("match", {})
                    reason = m.get("reasons", [""])[0]
                    console.print(f"  • [bold white]{j['title']}[/bold white] at [cyan]{j['company']}[/cyan] — [bold green]{m.get('score')}% Match[/bold green] ({j.get('salary') or '4-Day Week'})")
                    console.print(f"    [dim]{reason}[/dim]")

            if recs.get("grants"):
                console.print("\n[bold yellow]🚀 Top Matching Startup Grants & Capital:[/bold yellow]")
                for g in recs["grants"]:
                    m = g.get("match", {})
                    reason = m.get("reasons", [""])[0]
                    console.print(f"  • [bold white]{g['title']}[/bold white] ([magenta]{g['organization']}[/magenta]) — [bold green]{m.get('score')}% Match[/bold green] ({g.get('funding_amount') or 'Capital'})")
                    console.print(f"    [dim]{reason}[/dim]")
            console.print()
        else:
            console.print("[yellow]Usage: uv run main.py resume parse <file.pdf> [--save] or uv run main.py resume recs[/yellow]")


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
        console.print("\n[bold yellow]🤖 Milestone 11: AI Profile, Matching & Copilot:[/bold yellow]")
        console.print("  [cyan]uv run main.py profile view[/cyan]                - View candidate profile & skills")
        console.print("  [cyan]uv run main.py profile set --skills '...'[/cyan]  - Update profile skills or target roles")
        console.print("  [cyan]uv run main.py match jobs[/cyan]                  - Rank jobs by AI Profile Match Score")
        console.print("  [cyan]uv run main.py match opps[/cyan]                  - Rank scholarships by AI Match Score")
        console.print("  [cyan]uv run main.py copilot --type job --id 1[/cyan]   - 1-Click tailored cover letter generator")
        console.print("\n[bold yellow]🌐 Interactive Web Dashboard:[/bold yellow]")
        console.print("  [cyan]uv run main.py ui[/cyan]                          - Launch browser UI at http://127.0.0.1:8000")
        console.print("\n[bold yellow]⏰ Background Automation:[/bold yellow]")
        console.print("  [cyan]uv run main.py auto --interval 60[/cyan]          - Auto-scrape & alert every 60 mins")
        console.print("  [cyan]uv run main.py auto --once[/cyan]                 - Run 1 automated cycle & exit\n")


if __name__ == "__main__":
    main()
