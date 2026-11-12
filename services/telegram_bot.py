"""Telegram Alert Dispatcher Service (Milestone 13).

Delivers real-time, interactive opportunity, job, and grant alerts directly
to your phone via the free Telegram Bot API with inline action buttons.
"""

import logging
import os
from typing import Any, Dict, List, Optional
import httpx
from storage.db import OpportunityDB

logger = logging.getLogger("telegram_bot")


class TelegramAlertDispatcher:
    """Dispatches formatted alert cards and inline keyboards to Telegram users."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, db: Optional[OpportunityDB] = None):
        self.db = db or OpportunityDB()

    @property
    def bot_token(self) -> Optional[str]:
        """Retrieves token from env var or SQLite settings."""
        return os.getenv("TELEGRAM_BOT_TOKEN") or self.db.get_setting("telegram_bot_token")

    @property
    def target_chat_id(self) -> Optional[str]:
        """Retrieves target chat ID from env var or SQLite settings."""
        return os.getenv("TELEGRAM_CHAT_ID") or self.db.get_setting("telegram_chat_id")

    def is_configured(self) -> bool:
        """Checks if both bot token and target chat ID are present."""
        return bool(self.bot_token and self.target_chat_id)

    def get_bot_info(self) -> Dict[str, Any]:
        """Fetches bot username and identity from Telegram."""
        token = self.bot_token
        if not token:
            return {"configured": False, "error": "No bot token configured"}

        url = self.BASE_URL.format(token=token, method="getMe")
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                data = res.json()
                if data.get("ok"):
                    bot = data["result"]
                    return {
                        "configured": True,
                        "bot_id": bot.get("id"),
                        "first_name": bot.get("first_name"),
                        "username": bot.get("username"),
                        "chat_id": self.target_chat_id,
                        "link": f"https://t.me/{bot.get('username')}",
                    }
                return {"configured": False, "error": data.get("description", "Failed to get bot info")}
        except Exception as e:
            return {"configured": False, "error": str(e)}

    def detect_chat_id(self) -> Dict[str, Any]:
        """Checks getUpdates to automatically capture the chat ID of anyone who clicked Start."""
        token = self.bot_token
        if not token:
            return {"success": False, "error": "Bot token not configured"}

        url = self.BASE_URL.format(token=token, method="getUpdates")
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(url)
                data = res.json()
                if not data.get("ok"):
                    return {"success": False, "error": data.get("description", "Telegram API error")}

                results = data.get("result", [])
                if not results:
                    return {
                        "success": False,
                        "waiting": True,
                        "message": "No messages received yet. Please open Telegram, search @ScraperGaloreBot, and click 'Start' or send a message.",
                    }

                # Get latest message
                latest = results[-1]
                msg = latest.get("message") or latest.get("channel_post") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                first_name = chat.get("first_name", "User")
                username = chat.get("username", "")

                if chat_id:
                    self.db.set_setting("telegram_chat_id", str(chat_id))
                    if first_name:
                        self.db.set_setting("telegram_chat_user", f"{first_name} (@{username})")
                    return {
                        "success": True,
                        "chat_id": str(chat_id),
                        "user": f"{first_name} (@{username})",
                        "message": f"Successfully connected to {first_name}'s Telegram chat!",
                    }
                return {"success": False, "error": "Could not extract chat ID from updates"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def test_connection(self, token: Optional[str] = None, chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Sends a verification ping to validate the Telegram Bot Token and Chat ID."""
        use_token = token or self.bot_token
        use_chat = chat_id or self.target_chat_id

        if not use_token:
            return {"success": False, "error": "No Telegram Bot Token provided."}
        if not use_chat:
            return {
                "success": False,
                "error": "No target Telegram Chat ID found. Please open @ScraperGaloreBot and press 'Start' first.",
            }

        url = self.BASE_URL.format(token=use_token, method="sendMessage")
        payload = {
            "chat_id": use_chat,
            "text": (
                "⚡ <b>ScraperGalore Alert Radar Connected!</b>\n\n"
                "Your automated opportunity feed is now connected to your phone.\n\n"
                "✅ Scholarships & Fellowships\n"
                "✅ 4-Day Remote Jobs & Tech Gigs\n"
                "✅ Venture Grants & Accelerators\n\n"
                "Whenever high-match opportunities are scraped, you will receive an alert card right here with 1-click apply buttons."
            ),
            "parse_mode": "HTML",
        }

        try:
            with httpx.Client(timeout=12.0) as client:
                res = client.post(url, json=payload)
                data = res.json()
                if res.status_code == 200 and data.get("ok"):
                    return {"success": True, "message": "Test notification delivered successfully to your phone!"}
                return {"success": False, "error": data.get("description", "Unknown Telegram API error")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def send_opportunity_card(
        self,
        item: Dict[str, Any],
        item_type: str = "job",
        match: Optional[Dict[str, Any]] = None,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends a rich Telegram card with direct apply and pipeline action buttons."""
        use_token = self.bot_token
        use_chat = chat_id or self.target_chat_id

        if not use_token or not use_chat:
            return {
                "success": False,
                "simulated": True,
                "message": "Telegram chat not connected yet.",
                "preview": self._format_message_text(item, item_type, match),
            }

        text = self._format_message_text(item, item_type, match)
        apply_url = item.get("url") or item.get("official_portal") or item.get("apply_url") or "https://t.me/OHUB4AllET"

        # Interactive inline keyboard
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🔗 Direct Apply", "url": apply_url},
                    {"text": "⭐ Open Dashboard", "url": "http://127.0.0.1:8000"}
                ]
            ]
        }

        url = self.BASE_URL.format(token=use_token, method="sendMessage")
        payload = {
            "chat_id": use_chat,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
            "disable_web_page_preview": False,
        }

        try:
            with httpx.Client(timeout=12.0) as client:
                res = client.post(url, json=payload)
                data = res.json()
                if res.status_code == 200 and data.get("ok"):
                    return {"success": True, "message_id": data["result"]["message_id"]}
                return {"success": False, "error": data.get("description", "Telegram dispatch failed")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _format_message_text(
        self,
        item: Dict[str, Any],
        item_type: str,
        match: Optional[Dict[str, Any]],
    ) -> str:
        """Formats the HTML alert text with emoji badges, match score, and metadata."""
        title = item.get("title", "New Opportunity")

        if item_type == "job":
            company = item.get("company", "Remote Tech Company")
            salary = item.get("salary") or "Competitive / Negotiable"
            score = item.get("work_life_score")
            score_str = f"🌿 <b>Work-Life Balance:</b> {score}/100\n" if score else ""
            type_badge = "💼 <b>4-DAY REMOTE JOB RADAR</b>"
            sub = f"🏢 <b>Company:</b> {company}\n💰 <b>Compensation:</b> {salary}\n{score_str}"
        elif item_type == "grant":
            org = item.get("organization", "Venture Capital / Grant Fund")
            amt = item.get("funding_amount", "Non-Dilutive Grant")
            stage = item.get("stage", "Pre-Seed / Seed")
            deadline = item.get("deadline", "Open / Rolling")
            type_badge = "🚀 <b>TECH GRANT & ACCELERATOR</b>"
            sub = f"🏛️ <b>Organization:</b> {org}\n💵 <b>Capital:</b> {amt}\n🎯 <b>Stage:</b> {stage}\n⏳ <b>Deadline:</b> {deadline}\n"
        else:
            channel = item.get("channel_name", "Academic Portal")
            deadline = item.get("deadline", "Rolling")
            type_badge = "🎓 <b>SCHOLARSHIP / FELLOWSHIP</b>"
            sub = f"🏛️ <b>Host Feed:</b> @{channel}\n⏳ <b>Deadline:</b> {deadline}\n"

        match_section = ""
        if match:
            pct = match.get("score", 0)
            grade = match.get("grade", "Candidate Fit")
            matched_skills = ", ".join(match.get("matched_skills", [])[:4])
            skills_str = f"\n🎯 <b>Matched Skills:</b> {matched_skills}" if matched_skills else ""
            match_section = f"\n🤖 <b>AI Fit Score:</b> <b>{pct}%</b> ({grade}){skills_str}\n"

        return (
            f"{type_badge}\n\n"
            f"<b>{title}</b>\n\n"
            f"{sub}"
            f"{match_section}\n"
            f"⚡ <i>Delivered via ScraperGalore Dispatcher</i>"
        )
