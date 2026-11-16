"""Autonomous Background Scheduler & Real-Time Radar Service (Option 2).

Orchestrates hands-free recurring crawling across all scholarship, local, and
foreign job engines, captures structured execution audits, and automatically
pushes high-fit opportunity alerts directly to candidate phones via Telegram.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from storage.db import OpportunityDB
from services.matcher import ProfileMatcher
from services.telegram_bot import TelegramAlertDispatcher

from scrapers.job_scraper import JobScraper
from scrapers.wwr_scraper import WWRScraper
from scrapers.local_jobs_scraper import LocalJobsScraper
from scrapers.scholarship_directory_scraper import ScholarshipDirectoryScraper
from scrapers.ohub_web_scraper import OHUBWebScraper
from scrapers.universal_scraper import UniversalScraper

logger = logging.getLogger("autonomous_scheduler")


class AutonomousScheduler:
    """Manages autonomous crawling, execution logging, and automated Telegram radar alerts."""

    def __init__(self, db: Optional[OpportunityDB] = None):
        self.db = db or OpportunityDB()
        self.telegram = TelegramAlertDispatcher(self.db)
        self.is_crawling: bool = False
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.last_run_at: Optional[str] = None
        self.next_run_at: Optional[str] = None
        self.last_summary: Optional[Dict[str, Any]] = None

        # Check DB for previous last run timestamp
        last_stat = self.db.get_crawl_stats()
        if last_stat.get("last_run"):
            self.last_run_at = last_stat["last_run"].get("completed_at")
            if self.last_run_at:
                try:
                    last_dt = datetime.fromisoformat(self.last_run_at.replace("Z", ""))
                    self.next_run_at = (last_dt + timedelta(hours=self.interval_hours)).isoformat()
                except Exception:
                    self.next_run_at = (datetime.utcnow() + timedelta(hours=self.interval_hours)).isoformat()

    # =========================================================================
    # Configuration Properties (Persisted in SQLite settings)
    # =========================================================================

    @property
    def enabled(self) -> bool:
        """Whether autonomous scheduled crawls are active."""
        val = self.db.get_setting("scheduler_enabled", "true")
        return val.lower() in ("true", "1", "yes")

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self.db.set_setting("scheduler_enabled", "true" if value else "false")
        if value:
            self._schedule_next()

    @property
    def interval_hours(self) -> int:
        """Interval between autonomous runs in hours (1, 3, 6, 12, 24)."""
        val = self.db.get_setting("scheduler_interval_hours", "6")
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 6

    @interval_hours.setter
    def interval_hours(self, hours: int) -> None:
        safe_hours = max(1, int(hours))
        self.db.set_setting("scheduler_interval_hours", str(safe_hours))
        self._schedule_next()

    @property
    def auto_telegram(self) -> bool:
        """Whether to automatically ping Telegram on newly discovered high-fit opportunities."""
        val = self.db.get_setting("scheduler_auto_telegram", "true")
        return val.lower() in ("true", "1", "yes")

    @auto_telegram.setter
    def auto_telegram(self, value: bool) -> None:
        self.db.set_setting("scheduler_auto_telegram", "true" if value else "false")

    @property
    def min_score_threshold(self) -> int:
        """Minimum fit score required to trigger an automatic Telegram phone alert."""
        val = self.db.get_setting("scheduler_min_score", "85")
        try:
            return max(50, min(100, int(val)))
        except (ValueError, TypeError):
            return 85

    @min_score_threshold.setter
    def min_score_threshold(self, score: int) -> None:
        safe_score = max(50, min(100, int(score)))
        self.db.set_setting("scheduler_min_score", str(safe_score))

    def _schedule_next(self) -> None:
        """Calculates and updates the next run timestamp."""
        now = datetime.utcnow()
        self.next_run_at = (now + timedelta(hours=self.interval_hours)).isoformat()

    # =========================================================================
    # Service Lifecycle: Background Daemon Thread
    # =========================================================================

    def start(self) -> None:
        """Starts the autonomous scheduling background daemon."""
        if self._thread and self._thread.is_alive():
            logger.info("Autonomous scheduler is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="AutonomousSchedulerThread", daemon=True)
        self._thread.start()
        logger.info("Autonomous scheduler background daemon started successfully.")

    def stop(self) -> None:
        """Signals the background daemon to terminate."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Autonomous scheduler background daemon stopped.")

    def _worker_loop(self) -> None:
        """Main periodic polling loop."""
        logger.info("Autonomous scheduler poll loop initialized.")
        while not self._stop_event.is_set():
            try:
                if self.enabled:
                    now = datetime.utcnow()
                    should_run = False

                    if not self.last_run_at:
                        should_run = True
                    else:
                        try:
                            last_dt = datetime.fromisoformat(self.last_run_at.replace("Z", ""))
                            elapsed = (now - last_dt).total_seconds()
                            if elapsed >= (self.interval_hours * 3600):
                                should_run = True
                        except Exception:
                            should_run = True

                    if should_run and not self.is_crawling:
                        logger.info("Interval trigger elapsed; starting autonomous crawl cycle.")
                        self.run_crawl_cycle(triggered_by="autonomous")

            except Exception as e:
                logger.error(f"Error in scheduler worker loop: {e}", exc_info=True)

            # Sleep in small slices to allow rapid shutdown response
            for _ in range(30):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    # =========================================================================
    # Crawl Execution Cycle
    # =========================================================================

    def trigger_now(self, triggered_by: str = "manual") -> Dict[str, Any]:
        """Triggers an immediate crawl cycle in a non-blocking background thread."""
        with self._lock:
            if self.is_crawling:
                return {
                    "success": False,
                    "status": "busy",
                    "message": "A crawl cycle is already executing. Please wait for it to complete.",
                }

            thread = threading.Thread(
                target=self.run_crawl_cycle,
                args=(triggered_by,),
                name="ManualCrawlThread",
                daemon=True,
            )
            thread.start()
            return {
                "success": True,
                "status": "initiated",
                "message": f"Autonomous crawl cycle initiated ({triggered_by}). Monitoring feeds in background.",
            }

    def run_crawl_cycle(self, triggered_by: str = "autonomous") -> Dict[str, Any]:
        """Executes all scraping feeds sequentially, records audits, and dispatches alerts."""
        with self._lock:
            if self.is_crawling:
                return {"status": "skipped", "message": "Crawl already in progress."}
            self.is_crawling = True

        cycle_start = datetime.utcnow()
        cycle_start_str = cycle_start.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"--- Starting Autonomous Crawl Cycle ({triggered_by}) at {cycle_start_str} ---")

        engine_results = []
        total_scraped = 0
        total_new = 0

        # Define all available crawling pipelines
        engines = [
            {
                "id": "ohub_portal",
                "name": "OHUB Opportunities Portal",
                "runner": lambda: OHUBWebScraper(self.db).scrape_all_categories(limit_per_cat=8),
            },
            {
                "id": "scholars4dev",
                "name": "Scholars4Dev Directory",
                "runner": lambda: ScholarshipDirectoryScraper(self.db).scrape_scholars4dev(limit=10),
            },
            {
                "id": "ethio_scholarships",
                "name": "Ethio Scholarship Telegram",
                "runner": lambda: ScholarshipDirectoryScraper(self.db).scrape_ethio_scholarship_telegram(limit=12),
            },
            {
                "id": "carraadesk",
                "name": "Carraadesk Academic Feed",
                "runner": lambda: ScholarshipDirectoryScraper(self.db).scrape_carraadesk(limit=10),
            },
            {
                "id": "jobs_ethiojobs",
                "name": "Ethiojobs Board",
                "runner": lambda: LocalJobsScraper(self.db).scrape_ethiojobs(limit=15),
            },
            {
                "id": "jobs_reporter",
                "name": "Ethiopian Reporter Jobs",
                "runner": lambda: LocalJobsScraper(self.db).scrape_reporter_jobs(limit=12),
            },
            {
                "id": "jobs_elelan",
                "name": "Elelan Jobs (Addis Ababa)",
                "runner": lambda: LocalJobsScraper(self.db).scrape_elelan_jobs(limit=8),
            },
            {
                "id": "jobs_remoteok",
                "name": "RemoteOK International Tech",
                "runner": lambda: LocalJobsScraper(self.db).scrape_remoteok(limit=20),
            },
            {
                "id": "jobs_4dayweek",
                "name": "4-Day Week Remote Jobs",
                "runner": lambda: self._run_4dayweek(),
            },
            {
                "id": "jobs_wwr",
                "name": "WeWorkRemotely Feed",
                "runner": lambda: self._run_wwr(),
            },
            {
                "id": "custom_sources",
                "name": "Universal Custom Feeds",
                "runner": lambda: self._run_custom_sources(),
            },
        ]

        for eng in engines:
            e_id = eng["id"]
            e_name = eng["name"]
            t0 = time.time()
            eng_start = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            try:
                res = eng["runner"]()
                duration_ms = int((time.time() - t0) * 1000)
                eng_end = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

                # Normalize results across different scraper shapes
                scraped = res.get("scraped") or res.get("total_scraped") or 0
                new_ins = res.get("new_inserted") or res.get("new") or res.get("total_new") or res.get("new_jobs") or 0
                status = "success" if res.get("success", True) else "failed"
                err_msg = res.get("error")

                self.db.log_crawl(
                    engine_id=e_id,
                    engine_name=e_name,
                    started_at=eng_start,
                    completed_at=eng_end,
                    duration_ms=duration_ms,
                    items_scraped=scraped,
                    new_inserted=new_ins,
                    status=status,
                    error_message=err_msg,
                    triggered_by=triggered_by,
                )

                total_scraped += scraped
                total_new += new_ins
                engine_results.append({
                    "id": e_id,
                    "name": e_name,
                    "status": status,
                    "duration_ms": duration_ms,
                    "scraped": scraped,
                    "new_inserted": new_ins,
                })
                logger.info(f"Engine [{e_id}] completed in {duration_ms}ms: {scraped} scraped, {new_ins} new.")

            except Exception as e:
                duration_ms = int((time.time() - t0) * 1000)
                eng_end = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                err_str = str(e)
                logger.error(f"Engine [{e_id}] failed: {err_str}")

                self.db.log_crawl(
                    engine_id=e_id,
                    engine_name=e_name,
                    started_at=eng_start,
                    completed_at=eng_end,
                    duration_ms=duration_ms,
                    items_scraped=0,
                    new_inserted=0,
                    status="failed",
                    error_message=err_str,
                    triggered_by=triggered_by,
                )
                engine_results.append({
                    "id": e_id,
                    "name": e_name,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "scraped": 0,
                    "new_inserted": 0,
                    "error": err_str,
                })

        # =====================================================================
        # Automated Telegram Phone Radar on High-Fit Discovered Opportunities
        # =====================================================================
        telegram_alerts_sent = 0
        if self.auto_telegram and self.telegram.is_configured() and total_new > 0:
            try:
                telegram_alerts_sent = self._dispatch_radar_alerts(cycle_start_str)
            except Exception as e:
                logger.error(f"Error during autonomous Telegram alert dispatch: {e}")

        cycle_end = datetime.utcnow()
        self.last_run_at = cycle_end.isoformat()
        self._schedule_next()

        cycle_duration = int((time.time() - cycle_start.timestamp()) * 1000)
        self.last_summary = {
            "completed_at": self.last_run_at,
            "duration_ms": cycle_duration,
            "total_scraped": total_scraped,
            "total_new": total_new,
            "engines_run": len(engine_results),
            "telegram_alerts_sent": telegram_alerts_sent,
            "engines": engine_results,
        }

        self.is_crawling = False
        logger.info(f"--- Crawl Cycle Complete in {cycle_duration}ms: {total_new} new items discovered ---")
        return self.last_summary

    def _run_4dayweek(self) -> Dict[str, Any]:
        """Helper to run 4dayweek scraper and persist."""
        scraper = JobScraper()
        jobs = scraper.scrape_4dayweek(limit=25)
        new_cnt = sum(1 for j in jobs if self.db.save_job(j))
        return {"success": True, "scraped": len(jobs), "new_inserted": new_cnt}

    def _run_wwr(self) -> Dict[str, Any]:
        """Helper to run WeWorkRemotely RSS feed scraper."""
        scraper = WWRScraper()
        jobs = scraper.scrape(limit=25)
        new_cnt = sum(1 for j in jobs if self.db.save_job(j))
        return {"success": True, "scraped": len(jobs), "new_inserted": new_cnt}

    def _run_custom_sources(self) -> Dict[str, Any]:
        """Helper to run user-defined custom scrapers."""
        scraper = UniversalScraper(self.db)
        results = scraper.scrape_all_active()
        total_scraped = sum(r.get("scraped", 0) for r in results)
        total_new = sum(r.get("new", 0) for r in results)
        return {"success": True, "scraped": total_scraped, "new_inserted": total_new}

    def _dispatch_radar_alerts(self, since_str: str) -> int:
        """Finds items discovered in this run that exceed the fit threshold and dispatches Telegram cards."""
        new_records = self.db.get_recent_new_items(since_str)
        profile = self.db.get_user_profile()
        alerts_sent = 0

        # Evaluate opportunities (scholarships/fellowships)
        for opp in new_records.get("opportunities", []):
            match = ProfileMatcher.match_item(profile, opp, item_type="opportunity")
            if match.get("score", 0) >= self.min_score_threshold:
                try:
                    res = self.telegram.send_opportunity_card(opp, item_type="opportunity", match=match)
                    if res.get("success"):
                        alerts_sent += 1
                        time.sleep(1.2)  # Respect Telegram rate limits
                except Exception as e:
                    logger.warning(f"Failed to push opportunity alert {opp.get('id')}: {e}")

        # Evaluate jobs
        for job in new_records.get("jobs", []):
            match = ProfileMatcher.match_item(profile, job, item_type="job")
            if match.get("score", 0) >= self.min_score_threshold:
                try:
                    res = self.telegram.send_opportunity_card(job, item_type="job", match=match)
                    if res.get("success"):
                        alerts_sent += 1
                        time.sleep(1.2)
                except Exception as e:
                    logger.warning(f"Failed to push job alert {job.get('id')}: {e}")

        logger.info(f"Dispatched {alerts_sent} high-fit radar alerts to Telegram.")
        return alerts_sent

    # =========================================================================
    # Status & Metrics
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Returns the full runtime status and performance statistics of the scheduler."""
        stats = self.db.get_crawl_stats()
        return {
            "enabled": self.enabled,
            "is_crawling": self.is_crawling,
            "interval_hours": self.interval_hours,
            "auto_telegram": self.auto_telegram,
            "min_score_threshold": self.min_score_threshold,
            "telegram_configured": self.telegram.is_configured(),
            "last_run_at": self.last_run_at,
            "next_run_at": self.next_run_at,
            "last_summary": self.last_summary,
            "stats": stats,
        }
