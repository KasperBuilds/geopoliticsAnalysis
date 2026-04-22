"""
SENTINEL — PDF Report Generator
Generates a professional dark-themed intelligence briefing PDF using ReportLab.
"""

import io
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

from analysts.base_analyst import AnalystBrief
from utils.logger import get_logger

log = get_logger("pdf_report")

# ── Colors ──────────────────────────────────────────────────
BG = HexColor("#0d1117")
CARD_BG = HexColor("#161b22")
ACCENT = HexColor("#00b4f0")
WHITE = HexColor("#e6edf3")
DIM = HexColor("#8b949e")
RED = HexColor("#f85149")
AMBER = HexColor("#ffb900")
GREEN = HexColor("#3fb950")
DIVIDER = HexColor("#30363d")

URGENCY_COLORS = {"CRITICAL": RED, "ELEVATED": AMBER, "ROUTINE": GREEN}

# ── Page ────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4
MARGIN = 50
CONTENT_W = PAGE_W - 2 * MARGIN
BOTTOM_MARGIN = 60


class PDFReportGenerator:
    """Generates a dark-themed PDF intelligence report from analyst briefs."""

    def __init__(self):
        self.page_num = 0
        self._briefs = []

    def generate(self, briefs: list[AnalystBrief]) -> bytes | None:
        if not briefs:
            return None
        try:
            self._briefs = briefs
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=A4)
            c.setTitle("SENTINEL Intelligence Brief")
            c.setAuthor("SENTINEL System")

            self.page_num = 0
            y = self._new_page(c)

            # Overall urgency
            uo = {"CRITICAL": 3, "ELEVATED": 2, "ROUTINE": 1}
            best = max(briefs, key=lambda b: uo.get(b.overall_urgency, 0))
            ucolor = URGENCY_COLORS.get(best.overall_urgency, GREEN)

            y = self._draw_header(c, y, best.overall_urgency, ucolor)

            for brief in briefs:
                y = self._draw_analyst(c, y, brief)

            # Singapore implications
            impls = []
            for b in briefs:
                impls.extend(b.singapore_implications[:3])
            if impls:
                y = self._draw_list_section(c, y, "SINGAPORE IMPLICATIONS", impls[:5], ACCENT)

            # Watchlist
            watch = []
            for b in briefs:
                watch.extend(b.watchlist[:3])
            if watch:
                y = self._draw_list_section(c, y, "WATCHLIST", watch[:5], AMBER)

            self._draw_footer(c)
            c.save()
            buf.seek(0)
            data = buf.getvalue()
            log.info("PDF report generated (%d KB, %d pages)", len(data) // 1024, self.page_num)
            return data
        except Exception as e:
            log.error("PDF generation failed: %s", str(e))
            return None

    # ── Page Management ─────────────────────────────────────

    def _new_page(self, c):
        if self.page_num > 0:
            self._draw_footer(c)
            c.showPage()
        self.page_num += 1
        c.setFillColor(BG)
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        c.setFillColor(ACCENT)
        c.rect(0, PAGE_H - 4, PAGE_W, 4, fill=1, stroke=0)
        return PAGE_H - 20

    def _need_page(self, c, y, needed):
        if y - needed < BOTTOM_MARGIN:
            y = self._new_page(c)
        return y

    # ── Header ──────────────────────────────────────────────

    def _draw_header(self, c, y, urgency, ucolor):
        y -= 30
        c.setFont("Helvetica-Bold", 28)
        c.setFillColor(ACCENT)
        c.drawString(MARGIN, y, "SENTINEL")

        tw = c.stringWidth("SENTINEL", "Helvetica-Bold", 28)
        c.setFont("Helvetica", 16)
        c.setFillColor(WHITE)
        c.drawString(MARGIN + tw + 12, y + 4, "INTELLIGENCE BRIEF")
        y -= 25

        now = datetime.now(timezone.utc).strftime("%d %b %Y  |  %H%M UTC")
        c.setFont("Helvetica", 10)
        c.setFillColor(DIM)
        c.drawString(MARGIN, y, now)

        # Threat badge (right side)
        btxt = f"{urgency} THREAT LEVEL"
        bw = c.stringWidth(btxt, "Helvetica-Bold", 10) + 30
        bx = PAGE_W - MARGIN - bw
        c.setStrokeColor(ucolor)
        c.setLineWidth(0.5)
        c.roundRect(bx, y - 4, bw, 18, 4, fill=0, stroke=1)
        c.setFillColor(ucolor)
        c.circle(bx + 10, y + 5, 4, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(bx + 20, y, btxt)
        y -= 20

        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.5)
        c.line(MARGIN, y, PAGE_W - MARGIN, y)
        return y - 15

    # ── Analyst Section ─────────────────────────────────────

    def _draw_analyst(self, c, y, brief):
        labels = {
            "Defence Strategist": "DEFENCE ANALYSIS",
            "Geoeconomic Analyst": "GEOECONOMIC ANALYSIS",
        }
        label = labels.get(brief.analyst_role, brief.analyst_role.upper())

        y = self._need_page(c, y, 120)

        # Section header
        c.setFillColor(ACCENT)
        c.rect(MARGIN, y - 2, 3, 16, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN + 10, y, label)
        y -= 25

        # Headline
        for line in simpleSplit(brief.headline, "Helvetica-Bold", 12, CONTENT_W - 10):
            y = self._need_page(c, y, 16)
            c.setFont("Helvetica-Bold", 12)
            c.setFillColor(WHITE)
            c.drawString(MARGIN + 8, y, line)
            y -= 16
        y -= 5

        # Executive summary
        for line in simpleSplit(brief.executive_summary, "Helvetica", 9, CONTENT_W - 10):
            y = self._need_page(c, y, 14)
            c.setFont("Helvetica", 9)
            c.setFillColor(DIM)
            c.drawString(MARGIN + 8, y, line)
            y -= 14
        y -= 10

        # Development cards
        for i, dev in enumerate(brief.key_developments[:5], 1):
            y = self._draw_dev_card(c, y, i, dev)
            y -= 5

        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.5)
        c.line(MARGIN, y, PAGE_W - MARGIN, y)
        return y - 15

    # ── Development Card ────────────────────────────────────

    def _draw_dev_card(self, c, y, num, dev):
        dc = URGENCY_COLORS.get(dev.urgency, GREEN)
        h_lines = simpleSplit(dev.headline, "Helvetica-Bold", 11, CONTENT_W - 60)
        a_lines = simpleSplit(dev.analysis[:250], "Helvetica", 9, CONTENT_W - 60)[:4]

        src = ""
        if dev.source_urls:
            src = " | ".join(dev.source_urls[:2])
        elif dev.sources:
            src = " | ".join(dev.sources[:2])

        card_h = 15 + len(h_lines) * 15 + len(a_lines) * 13 + (12 if src else 0) + 10
        y = self._need_page(c, y, card_h + 10)

        # Card bg
        c.setFillColor(CARD_BG)
        c.roundRect(MARGIN, y - card_h + 12, CONTENT_W, card_h, 6, fill=1, stroke=0)
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.5)
        c.roundRect(MARGIN, y - card_h + 12, CONTENT_W, card_h, 6, fill=0, stroke=1)

        # Left accent
        c.setFillColor(dc)
        c.rect(MARGIN + 1, y - card_h + 18, 3, card_h - 12, fill=1, stroke=0)

        # Number circle
        c.setFillColor(dc)
        c.circle(MARGIN + 18, y - 2, 9, fill=1, stroke=0)
        c.setFillColor(BG)
        c.setFont("Helvetica-Bold", 9)
        nw = c.stringWidth(str(num), "Helvetica-Bold", 9)
        c.drawString(MARGIN + 18 - nw / 2, y - 5, str(num))

        # Headline
        cy = y
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(WHITE)
        for line in h_lines:
            c.drawString(MARGIN + 35, cy, line)
            cy -= 15

        # Analysis
        cy -= 3
        c.setFont("Helvetica", 9)
        c.setFillColor(DIM)
        for line in a_lines:
            c.drawString(MARGIN + 35, cy, line)
            cy -= 13

        # Sources
        if src:
            cy -= 2
            c.setFont("Helvetica", 7)
            c.setFillColor(DIM)
            max_w = CONTENT_W - 50
            if c.stringWidth(src, "Helvetica", 7) > max_w:
                while c.stringWidth(src + "...", "Helvetica", 7) > max_w and len(src) > 10:
                    src = src[:-1]
                src += "..."
            c.drawString(MARGIN + 35, cy, f"-> {src}")

        return y - card_h - 3

    # ── List Sections (SG Implications / Watchlist) ─────────

    def _draw_list_section(self, c, y, title, items, bullet_color):
        y = self._need_page(c, y, 80)

        c.setFillColor(ACCENT)
        c.rect(MARGIN, y - 2, 3, 16, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN + 10, y, title)
        y -= 25

        for item in items:
            lines = simpleSplit(item, "Helvetica", 9, CONTENT_W - 25)
            y = self._need_page(c, y, len(lines) * 13 + 8)

            c.setFillColor(bullet_color)
            c.circle(MARGIN + 8, y + 3, 2.5, fill=1, stroke=0)

            c.setFont("Helvetica", 9)
            c.setFillColor(WHITE)
            for line in lines:
                c.drawString(MARGIN + 18, y, line)
                y -= 13
            y -= 5

        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.5)
        c.line(MARGIN, y, PAGE_W - MARGIN, y)
        return y - 15

    # ── Footer ──────────────────────────────────────────────

    def _draw_footer(self, c):
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.5)
        c.line(MARGIN, 40, PAGE_W - MARGIN, 40)

        c.setFont("Helvetica", 7)
        c.setFillColor(DIM)
        c.drawString(MARGIN, 28, "SENTINEL -- Autonomous Geopolitical Intelligence")

        pt = f"Page {self.page_num}"
        pw = c.stringWidth(pt, "Helvetica", 7)
        c.drawString(PAGE_W - MARGIN - pw, 28, pt)
