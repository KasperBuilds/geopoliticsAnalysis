"""
SENTINEL — Infographic Generator
Renders visual intelligence summary infographics using Pillow.
Produces a readable, data-rich visual brief for quick mobile consumption.
"""

import io
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from analysts.base_analyst import AnalystBrief
from utils.logger import get_logger

log = get_logger("infographic")

# ── Color Palette ───────────────────────────────────────────
BG = (13, 17, 23)
CARD = (22, 27, 34)
ACCENT = (0, 180, 240)
WHITE = (230, 237, 243)
DIM = (125, 133, 144)
RED = (248, 81, 73)
AMBER = (255, 185, 0)
GREEN = (63, 185, 80)
DIVIDER = (48, 54, 61)

URGENCY_COLORS = {"CRITICAL": RED, "ELEVATED": AMBER, "ROUTINE": GREEN}

# ── Layout Constants ────────────────────────────────────────
WIDTH = 1080
MARGIN = 60
CONTENT_W = WIDTH - 2 * MARGIN


class InfographicGenerator:
    """Generates Pillow-rendered infographic images from analyst briefs."""

    def __init__(self):
        self.fonts = {}
        self._load_fonts()

    def _try_load_font(self, size, bold=False):
        """Try loading a font from known system paths."""
        regular = [
            ("/System/Library/Fonts/Helvetica.ttc", 0),
            ("/System/Library/Fonts/SFNSText.ttf", None),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None),
            ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", None),
        ]
        bold_paths = [
            ("/System/Library/Fonts/Helvetica.ttc", 1),
            ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
            ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", None),
        ]
        for path, index in (bold_paths if bold else regular):
            try:
                kwargs = {"index": index} if index is not None else {}
                return ImageFont.truetype(path, size, **kwargs)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _load_fonts(self):
        """Load all required font sizes."""
        specs = {
            "title": (36, True), "subtitle": (22, False),
            "section": (26, True), "headline": (22, True),
            "body": (20, False), "small": (16, False), "badge": (18, True),
        }
        for name, (size, bold) in specs.items():
            self.fonts[name] = self._try_load_font(size, bold)

    def _wrap(self, draw, text, font, max_w):
        """Word-wrap text to fit within max_w pixels."""
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = f"{cur} {w}".strip()
            if draw.textlength(test, font=font) <= max_w:
                cur = test
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    def _dark(self, color, factor=6):
        """Darken a color for badge backgrounds."""
        return tuple(c // factor for c in color)

    def generate(self, briefs: list[AnalystBrief]) -> bytes | None:
        """Generate an infographic image from analyst briefs."""
        if not briefs:
            return None
        try:
            # Two-pass: measure height, then draw
            tmp = Image.new("RGB", (WIDTH, 100))
            tmp_draw = ImageDraw.Draw(tmp)
            h = self._measure(tmp_draw, briefs)

            img = Image.new("RGB", (WIDTH, h), BG)
            draw = ImageDraw.Draw(img)
            self._render(draw, briefs)

            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            buf.seek(0)
            data = buf.getvalue()
            log.info("Infographic generated (%d KB, %dx%d)", len(data) // 1024, WIDTH, h)
            return data
        except Exception as e:
            log.error("Infographic generation failed: %s", str(e))
            return None

    # ── Measurement Pass ────────────────────────────────────

    def _measure(self, draw, briefs):
        y = MARGIN
        y += 50 + 30 + 45 + 30  # header block

        for brief in briefs:
            y += 40  # section header
            y += len(self._wrap(draw, brief.headline, self.fonts["headline"], CONTENT_W - 20)) * 28 + 10
            y += len(self._wrap(draw, brief.executive_summary, self.fonts["body"], CONTENT_W - 20)) * 26 + 20

            for dev in brief.key_developments[:4]:
                h_lines = self._wrap(draw, dev.headline, self.fonts["headline"], CONTENT_W - 100)
                a_lines = self._wrap(draw, dev.analysis[:200], self.fonts["body"], CONTENT_W - 100)[:3]
                y += 20 + len(h_lines) * 28 + len(a_lines) * 26 + 30
            y += 30

        # Singapore implications
        for brief in briefs:
            for impl in brief.singapore_implications[:3]:
                y += len(self._wrap(draw, impl, self.fonts["body"], CONTENT_W - 30)) * 26 + 8
        if any(b.singapore_implications for b in briefs):
            y += 60

        y += 50  # footer
        return y + MARGIN

    # ── Render Pass ─────────────────────────────────────────

    def _render(self, draw, briefs):
        urgency_order = {"CRITICAL": 3, "ELEVATED": 2, "ROUTINE": 1}
        overall = max(briefs, key=lambda b: urgency_order.get(b.overall_urgency, 0)).overall_urgency
        ucolor = URGENCY_COLORS.get(overall, GREEN)
        y = MARGIN

        # ── Top accent bar ──
        draw.rectangle([(0, 0), (WIDTH, 4)], fill=ACCENT)

        # ── Title ──
        draw.text((MARGIN, y), "SENTINEL", font=self.fonts["title"], fill=ACCENT)
        tw = draw.textlength("SENTINEL", font=self.fonts["title"])
        draw.text((MARGIN + tw + 15, y + 8), "INTELLIGENCE BRIEF", font=self.fonts["subtitle"], fill=WHITE)
        y += 50

        # ── Date ──
        now = datetime.now(timezone.utc).strftime("%d %b %Y  |  %H%M UTC")
        draw.text((MARGIN, y), now, font=self.fonts["small"], fill=DIM)
        y += 30

        # ── Threat level badge ──
        badge_text = f" {overall} THREAT LEVEL "
        bw = draw.textlength(badge_text, font=self.fonts["badge"]) + 40
        draw.rounded_rectangle(
            [(MARGIN, y), (MARGIN + bw, y + 34)],
            radius=8, fill=self._dark(ucolor), outline=ucolor,
        )
        draw.ellipse((MARGIN + 12, y + 12, MARGIN + 22, y + 22), fill=ucolor)
        draw.text((MARGIN + 30, y + 7), f"{overall} THREAT LEVEL", font=self.fonts["badge"], fill=ucolor)
        y += 45

        draw.rectangle([(MARGIN, y), (WIDTH - MARGIN, y + 1)], fill=DIVIDER)
        y += 20

        # ── Analyst Sections ──
        labels = {"Defence Strategist": "DEFENCE ANALYSIS", "Geoeconomic Analyst": "GEOECONOMIC ANALYSIS"}

        for brief in briefs:
            label = labels.get(brief.analyst_role, brief.analyst_role.upper())
            # Section header with left accent bar
            draw.rectangle([(MARGIN, y + 2), (MARGIN + 4, y + 30)], fill=ACCENT)
            draw.text((MARGIN + 14, y), label, font=self.fonts["section"], fill=ACCENT)
            y += 40

            # Headline
            for line in self._wrap(draw, brief.headline, self.fonts["headline"], CONTENT_W - 20):
                draw.text((MARGIN + 10, y), line, font=self.fonts["headline"], fill=WHITE)
                y += 28
            y += 10

            # Executive summary
            for line in self._wrap(draw, brief.executive_summary, self.fonts["body"], CONTENT_W - 20):
                draw.text((MARGIN + 10, y), line, font=self.fonts["body"], fill=DIM)
                y += 26
            y += 15

            # Development cards
            for i, dev in enumerate(brief.key_developments[:4], 1):
                dc = URGENCY_COLORS.get(dev.urgency, GREEN)
                h_lines = self._wrap(draw, dev.headline, self.fonts["headline"], CONTENT_W - 100)
                a_lines = self._wrap(draw, dev.analysis[:200], self.fonts["body"], CONTENT_W - 100)[:3]
                card_h = 20 + len(h_lines) * 28 + len(a_lines) * 26 + 25

                # Card bg + left bar
                draw.rounded_rectangle(
                    [(MARGIN, y), (WIDTH - MARGIN, y + card_h)],
                    radius=10, fill=CARD, outline=DIVIDER,
                )
                draw.rectangle([(MARGIN, y + 8), (MARGIN + 4, y + card_h - 8)], fill=dc)

                # Number circle
                draw.ellipse((MARGIN + 16, y + 16, MARGIN + 38, y + 38), fill=dc)
                nt = str(i)
                nw = draw.textlength(nt, font=self.fonts["small"])
                draw.text((MARGIN + 27 - nw / 2, y + 18), nt, font=self.fonts["small"], fill=BG)

                # Headline lines
                cy = y + 15
                for line in h_lines:
                    draw.text((MARGIN + 50, cy), line, font=self.fonts["headline"], fill=WHITE)
                    cy += 28

                # Analysis lines
                cy += 2
                for line in a_lines:
                    draw.text((MARGIN + 50, cy), line, font=self.fonts["body"], fill=DIM)
                    cy += 26

                # Source attribution (bottom right of card)
                if dev.sources:
                    src = " · ".join(s for s in dev.sources[:2])
                    sw = draw.textlength(src, font=self.fonts["small"])
                    draw.text(
                        (WIDTH - MARGIN - sw - 15, y + card_h - 22),
                        src, font=self.fonts["small"], fill=DIM,
                    )

                y += card_h + 10

            y += 10
            draw.rectangle([(MARGIN, y), (WIDTH - MARGIN, y + 1)], fill=DIVIDER)
            y += 20

        # ── Singapore Implications ──
        all_impl = []
        for b in briefs:
            all_impl.extend(b.singapore_implications[:3])

        if all_impl:
            draw.rectangle([(MARGIN, y + 2), (MARGIN + 4, y + 30)], fill=ACCENT)
            draw.text((MARGIN + 14, y), "SINGAPORE IMPLICATIONS", font=self.fonts["section"], fill=ACCENT)
            y += 40

            for impl in all_impl[:5]:
                lines = self._wrap(draw, impl, self.fonts["body"], CONTENT_W - 30)
                # Bullet
                draw.ellipse((MARGIN + 10, y + 8, MARGIN + 16, y + 14), fill=ACCENT)
                first = True
                for line in lines:
                    x = MARGIN + 25 if first else MARGIN + 25
                    draw.text((x, y), line, font=self.fonts["body"], fill=WHITE)
                    y += 26
                    first = False
                y += 8
            y += 10

        # ── Footer ──
        draw.rectangle([(0, y), (WIDTH, y + 1)], fill=DIVIDER)
        y += 15
        draw.text((MARGIN, y), "SENTINEL -- Autonomous Geopolitical Intelligence", font=self.fonts["small"], fill=DIM)
