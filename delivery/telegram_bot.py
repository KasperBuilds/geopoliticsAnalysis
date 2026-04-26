"""
SENTINEL — Telegram Delivery Bot
Formats and delivers analyst briefs via Telegram with rich formatting.
Combines multiple analyst briefs into a single unified intelligence report.
Handles message splitting for the 4096-character limit.
"""

import asyncio
import io
from datetime import datetime, timezone

from telegram import Bot
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from analysts.base_analyst import AnalystBrief
from utils.logger import get_logger

log = get_logger("telegram")

# Telegram message character limit
MAX_MESSAGE_LENGTH = 4000  # Leave some margin from the 4096 hard limit


class TelegramDelivery:
    """Handles formatting and sending analyst briefs via Telegram."""

    def __init__(self):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            log.warning("Telegram credentials not configured — delivery will be skipped")
            self.bot = None
        else:
            self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
            self.chat_id = TELEGRAM_CHAT_ID

    def _split_message(self, text: str) -> list[str]:
        """
        Split a long message into chunks that fit within Telegram's limit.
        Splits on newlines to avoid breaking formatting.
        """
        if len(text) <= MAX_MESSAGE_LENGTH:
            return [text]

        chunks = []
        current_chunk = ""

        for line in text.split("\n"):
            if len(current_chunk) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                current_chunk += ("\n" + line) if current_chunk else line

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    async def _send_message(self, text: str):
        """Send a single message via Telegram."""
        if not self.bot:
            log.info("TELEGRAM [DRY RUN]:\n%s", text)
            return

        try:
            chunks = self._split_message(text)
            for i, chunk in enumerate(chunks):
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=chunk,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                if i < len(chunks) - 1:
                    await asyncio.sleep(0.5)  # Rate limiting between chunks

            log.info("Sent message (%d chars, %d chunks)", len(text), len(chunks))

        except Exception as e:
            log.error("Telegram send failed: %s", str(e))
            # Try sending without HTML parsing as fallback
            try:
                plain_text = text.replace("<b>", "").replace("</b>", "")
                plain_text = plain_text.replace("<i>", "").replace("</i>", "")
                chunks = self._split_message(plain_text)
                for chunk in chunks:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=chunk,
                        disable_web_page_preview=True,
                    )
                log.info("Sent message as plain text fallback")
            except Exception as e2:  # noqa: F841
                log.error("Telegram send failed even without HTML: %s", str(e2))

    def _format_tldr(self, briefs: list[AnalystBrief]) -> str:
        """
        Build a visual dashboard TL;DR message.
        Each development gets a card with icon, what, why, and SG impact.
        Designed for quick glance on mobile. Full detail lives in the PDF.
        """
        urgency_icons = {"CRITICAL": "🔴", "ELEVATED": "🟡", "ROUTINE": "🟢"}
        urgency_order = {"CRITICAL": 3, "ELEVATED": 2, "ROUTINE": 1}
        urgency_labels = {"CRITICAL": "Critical", "ELEVATED": "Elevated", "ROUTINE": "Routine"}

        overall = max(briefs, key=lambda b: urgency_order.get(b.overall_urgency, 0))
        urgency = overall.overall_urgency
        icon = urgency_icons.get(urgency, "⚪")
        label = urgency_labels.get(urgency, urgency.title())

        now = datetime.now(timezone.utc).strftime("%d %b %Y • %H%M UTC")

        lines = [
            "🛰️ <b>SENTINEL BRIEF — VISUAL DASHBOARD</b>",
            "",
            f"📅 {now} • {icon} {label}",
        ]

        # Development cards from all analysts
        for brief in briefs:
            for dev in brief.key_developments:
                dev_icon = dev.icon or "📌"
                lines.append("")
                lines.append(f"{dev_icon} <b>{dev.headline}</b>")

                # Use dashboard fields if available, fall back to analysis
                if dev.what:
                    lines.append(f"What: {dev.what}")
                if dev.why:
                    # Use context-appropriate label
                    why_label = "Why it matters" if "matter" not in dev.why.lower() else "Why"
                    lines.append(f"{why_label}: {dev.why}")
                elif dev.analysis:
                    # Truncate analysis to first sentence as fallback
                    first_sentence = dev.analysis.split(". ")[0] + "."
                    lines.append(f"Why: {first_sentence}")

                if dev.sg_impact:
                    lines.append(f"🇸🇬 Impact: {dev.sg_impact}")

        lines.extend(["", "📄 Full report attached below."])

        return "\n".join(lines)

    async def send_tldr(self, briefs: list[AnalystBrief]):
        """Send a short TL;DR summary message."""
        if not briefs:
            return
        tldr = self._format_tldr(briefs)
        log.info("Delivering TL;DR (%d chars)", len(tldr))
        await self._send_message(tldr)

    def send_tldr_sync(self, briefs: list[AnalystBrief]):
        """Synchronous wrapper for send_tldr."""
        asyncio.run(self.send_tldr(briefs))

    def _format_unified_brief(self, briefs: list[AnalystBrief]) -> str:
        """
        Combine multiple analyst briefs into a SINGLE unified intelligence report.
        No duplication — one cohesive message.
        """
        urgency_icons = {"CRITICAL": "🔴", "ELEVATED": "🟡", "ROUTINE": "🟢"}
        role_icons = {"Defence Strategist": "🎖️", "Geoeconomic Analyst": "📈"}

        # Determine overall urgency (highest of all analysts)
        urgency_order = {"CRITICAL": 3, "ELEVATED": 2, "ROUTINE": 1}
        overall = max(briefs, key=lambda b: urgency_order.get(b.overall_urgency, 0))
        overall_urgency = overall.overall_urgency
        urgency_icon = urgency_icons.get(overall_urgency, "⚪")

        now = datetime.now(timezone.utc).strftime("%d %b %Y • %H%M UTC")

        lines = [
            "🛰️ <b>SENTINEL INTELLIGENCE BRIEF</b>",
            f"📅 {now}",
            f"{urgency_icon} <b>{overall_urgency} THREAT LEVEL</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━",
        ]

        # Each analyst section
        for brief in briefs:
            icon = role_icons.get(brief.analyst_role, "📋")

            lines.extend([
                "",
                f"{icon} <b>{brief.analyst_role.upper()}</b>",
                "",
                f"📌 {brief.headline}",
                "",
                f"{brief.executive_summary}",
            ])

            # Key developments
            if brief.key_developments:
                lines.append("")
                for i, dev in enumerate(brief.key_developments, 1):
                    dev_icon = urgency_icons.get(dev.urgency, "⚪")
                    lines.append(f"{dev_icon} <b>[{i}] {dev.headline}</b>")
                    lines.append(f"{dev.analysis}")
                    # Show sources as clickable hyperlinks
                    if dev.source_urls:
                        lines.append(f"→ {' · '.join(dev.source_urls)}")
                    elif dev.sources:
                        lines.append(f"→ {', '.join(dev.sources)}")
                    lines.append("")

            # Singapore implications
            if brief.singapore_implications:
                lines.append(f"🇸🇬 <b>SINGAPORE IMPLICATIONS</b>")
                for impl in brief.singapore_implications:
                    lines.append(f"• {impl}")
                lines.append("")

            # Watchlist
            if brief.watchlist:
                lines.append(f"👁️ <b>WATCHLIST</b>")
                for item in brief.watchlist:
                    lines.append(f"• {item}")

            lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

        lines.extend([
            "",
            "🛰️ <i>SENTINEL — Autonomous Geopolitical Intelligence</i>",
        ])

        return "\n".join(lines)

    async def send_briefs(self, briefs: list[AnalystBrief]):
        """Send all analyst briefs as a single unified report."""
        if not briefs:
            log.warning("No briefs to deliver")
            return

        unified = self._format_unified_brief(briefs)
        log.info("Delivering unified brief (%d chars, %d analysts)", len(unified), len(briefs))
        await self._send_message(unified)
        log.info("Unified brief delivered successfully")

    def send_briefs_sync(self, briefs: list[AnalystBrief]):
        """Synchronous wrapper for send_briefs."""
        asyncio.run(self.send_briefs(briefs))

    async def _send_photo(self, image_bytes: bytes, caption: str = ""):
        """Send an image via Telegram."""
        if not self.bot:
            log.info("TELEGRAM [DRY RUN]: Would send infographic (%d KB)", len(image_bytes) // 1024)
            return

        try:
            photo_file = io.BytesIO(image_bytes)
            photo_file.name = "sentinel_brief.png"
            await self.bot.send_photo(
                chat_id=self.chat_id,
                photo=photo_file,
                caption=caption[:1024] if caption else None,  # Telegram caption limit
                parse_mode=ParseMode.HTML,
            )
            log.info("Sent infographic photo (%d KB)", len(image_bytes) // 1024)
        except Exception as e:
            log.error("Telegram photo send failed: %s", str(e))

    async def send_infographic(self, image_bytes: bytes, caption: str = ""):
        """Send an infographic image."""
        if not image_bytes:
            log.warning("No infographic image to send")
            return
        await self._send_photo(image_bytes, caption)

    def send_infographic_sync(self, image_bytes: bytes, caption: str = ""):
        """Synchronous wrapper for send_infographic."""
        asyncio.run(self.send_infographic(image_bytes, caption))

    async def _send_document(self, doc_bytes: bytes, filename: str, caption: str = ""):
        """Send a document file via Telegram."""
        if not self.bot:
            log.info("TELEGRAM [DRY RUN]: Would send document '%s' (%d KB)", filename, len(doc_bytes) // 1024)
            return

        try:
            doc_file = io.BytesIO(doc_bytes)
            doc_file.name = filename
            await self.bot.send_document(
                chat_id=self.chat_id,
                document=doc_file,
                caption=caption[:1024] if caption else None,
                parse_mode=ParseMode.HTML,
            )
            log.info("Sent document '%s' (%d KB)", filename, len(doc_bytes) // 1024)
        except Exception as e:
            log.error("Telegram document send failed: %s", str(e))

    async def send_pdf(self, pdf_bytes: bytes, caption: str = ""):
        """Send a PDF report."""
        if not pdf_bytes:
            log.warning("No PDF to send")
            return
        now = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        filename = f"SENTINEL_Brief_{now}.pdf"
        await self._send_document(pdf_bytes, filename, caption)

    def send_pdf_sync(self, pdf_bytes: bytes, caption: str = ""):
        """Synchronous wrapper for send_pdf."""
        asyncio.run(self.send_pdf(pdf_bytes, caption))

    async def send_status(self, message: str):
        """Send a system status message."""
        status_text = f"⚙️ <b>SENTINEL STATUS</b>\n{message}"
        await self._send_message(status_text)

    def send_status_sync(self, message: str):
        """Synchronous wrapper for send_status."""
        asyncio.run(self.send_status(message))
