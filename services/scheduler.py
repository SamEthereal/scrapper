"""Automated background scheduler for periodic opportunity and job scraping."""

import datetime
import time
from pathlib import Path
from typing import List, Optional

import schedule
from rich.console import Console

from parsers.job_parser import JobItem
from parsers.scholarship_parser import OpportunityItem, parse_post
from scrapers.job_scraper import JobScraper
from scrapers.telegram_scraper import TelegramScraper
from scrapers.web_scraper import WebScraper
from storage.db import OpportunityDB

console = Console()
LOG_FILE = Path("scraper_activity.log")


def log_activity(message: str) -> None:
    """Appends timestamped message to scraper_activity.log and prints to console."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    console.print(f"[dim]{timestamp}[/dim] {message}")

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception as e:
        console.print(f"[red]Logging error:[/red] {e}")


def send_desktop_alert(title: str, message: str) -> None:
    """Sends a desktop notification if supported, falling back gracefully without crashing."""
    import sys
    if sys.platform == "win32":
        try:
            import subprocess
            clean_title = title.replace("'", "").replace('"', '')
            clean_msg = message.replace("'", "").replace('"', '')
            ps_script = (
                "[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
                "$n = New-Object System.Windows.Forms.NotifyIcon; "
                "$n.Icon = [System.Drawing.SystemIcons]::Information; "
                "$n.Visible = $True; "
                f"$n.ShowBalloonTip(4000, '{clean_title}', '{clean_msg}', [System.Windows.Forms.ToolTipIcon]::Info); "
                "Start-Sleep -Milliseconds 300; $n.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass

    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="OpportunityHub",
            timeout=8,
        )
    except Exception:
        pass


class ScraperScheduler:
    """Manages scheduled background scraping tasks and alerts for new opportunities."""

    def __init__(self, db: Optional[OpportunityDB] = None):
        self.db = db or OpportunityDB()
        self.tg_scraper = TelegramScraper()
        self.web_scraper = WebScraper()
        self.job_scraper = JobScraper()

    def sync_scholarships(self) -> List[OpportunityItem]:
        """Scrapes Telegram feed and deep-scrapes new opportunity web portals."""
        new_items: List[OpportunityItem] = []
        try:
            raw_posts = self.tg_scraper.scrape_channel("https://t.me/OHUB4AllET", limit=8)
            for post in raw_posts:
                item = parse_post(post)
                if not item.is_opportunity:
                    continue

                portal = None
                highlights = None

                # Deep-scrape portal if specific link exists
                if item.apply_url and not item.apply_url.rstrip("/").endswith("/opportunities"):
                    try:
                        page_data = self.web_scraper.scrape(item.apply_url)
                        portal = page_data.apply_links[0] if page_data.apply_links else None
                        highlights = page_data.key_highlights
                    except Exception:
                        pass

                is_new = self.db.save_opportunity(
                    item,
                    official_portal=portal,
                    key_highlights=highlights,
                )
                if is_new:
                    new_items.append(item)

        except Exception as e:
            log_activity(f"[yellow]⚠ Scholarship scraper notice:[/yellow] {e}")

        return new_items

    def sync_jobs(self) -> List[JobItem]:
        """Scrapes remote 4-day jobs and saves new ones."""
        new_jobs: List[JobItem] = []
        try:
            jobs = self.job_scraper.scrape_4dayweek(limit=50)
            for j in jobs:
                is_new = self.db.save_job(j)
                if is_new:
                    new_jobs.append(j)
        except Exception as e:
            log_activity(f"[yellow]⚠ Job scraper notice:[/yellow] {e}")

        return new_jobs

    def run_cycle(self) -> None:
        """Executes a single check cycle across all scrapers."""
        log_activity("[bold cyan]▶ Starting scheduled scrape cycle...[/bold cyan]")

        new_opps = self.sync_scholarships()
        new_jobs = self.sync_jobs()

        total_new = len(new_opps) + len(new_jobs)

        if total_new > 0:
            summary = f"🎉 Found {len(new_opps)} new scholarship(s) and {len(new_jobs)} new job(s)!"
            log_activity(f"[bold green]{summary}[/bold green]")

            # Log titles of new discoveries
            for it in new_opps:
                log_activity(f"  🎓 [bold white]{it.title}[/bold white] (Deadline: {it.deadline_date or 'N/A'})")
            for j in new_jobs:
                log_activity(f"  💼 [bold white]{j.title}[/bold white] @ {j.company} ({j.salary or 'Salary N/A'})")

            # Trigger desktop alert
            send_desktop_alert(
                title="Opportunity Hub Alert",
                message=summary,
            )
        else:
            log_activity("[dim]Cycle finished: All scraped listings already in database (no new additions).[/dim]")

    def start(self, interval_minutes: int = 60, run_immediately: bool = True) -> None:
        """
        Starts the recurring scheduler loop.
        
        Args:
            interval_minutes: Minutes between scraping cycles.
            run_immediately: If True, executes the first cycle immediately on start.
        """
        log_activity(f"[bold green]✓ Scheduler activated![/bold green] Checking every [bold yellow]{interval_minutes}[/bold yellow] minute(s).")
        log_activity("[dim]Press Ctrl+C to stop the scheduler.[/dim]\n")

        if run_immediately:
            self.run_cycle()

        schedule.every(interval_minutes).minutes.do(self.run_cycle)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            log_activity("[bold yellow]Scheduler stopped by user.[/bold yellow]")
