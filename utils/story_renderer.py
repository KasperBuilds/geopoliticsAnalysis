"""
SENTINEL — Instagram Story Renderer
Deterministic Pillow rendering of three 1080×1920 Story images.
No generative image models — typography and layout only.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from analysts.story_brief import StoryBriefing
from utils.logger import get_logger
from utils.story_design import DEFAULT_STORY_DESIGN, StoryDesign

log = get_logger("story_renderer")


class StoryRenderError(Exception):
    """Raised when Story image rendering fails."""


class StoryRenderer:
    """Renders exactly three Instagram Story PNGs from a validated briefing."""

    def __init__(self, design: StoryDesign | None = None):
        self.design = design or DEFAULT_STORY_DESIGN
        self.fonts: dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}
        self._load_fonts()

    def _try_load_font(self, size: int, bold: bool = False):
        paths = self.design.font_bold_paths if bold else self.design.font_regular_paths
        for path, index in paths:
            try:
                kwargs = {"index": index} if index is not None else {}
                return ImageFont.truetype(path, size, **kwargs)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _load_fonts(self) -> None:
        d = self.design
        specs = {
            "brand": (d.font_brand, True),
            "date": (d.font_date, False),
            "risk": (d.font_risk, True),
            "headline": (d.font_headline, True),
            "overview": (d.font_overview, False),
            "section": (d.font_section, True),
            "dev_number": (d.font_dev_number, True),
            "dev_title": (d.font_dev_title, True),
            "dev_body": (d.font_dev_body, False),
            "impact_area": (d.font_impact_area, True),
            "impact_body": (d.font_impact_body, False),
            "watch": (d.font_watch, False),
            "small": (d.font_small, False),
        }
        for name, (size, bold) in specs.items():
            self.fonts[name] = self._try_load_font(size, bold)

    def _wrap(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font,
        max_w: int,
        max_lines: int | None = None,
    ) -> list[str]:
        """Word-wrap with optional hard line cap and safe truncation."""
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            if draw.textlength(test, font=font) <= max_w:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            return [""]

        if max_lines is not None and len(lines) > max_lines:
            kept = lines[:max_lines]
            last = kept[-1]
            ellipsis = self.design.ellipsis
            while last and draw.textlength(last + ellipsis, font=font) > max_w:
                last = last[:-1].rstrip()
            kept[-1] = (last + ellipsis) if last else ellipsis
            return kept
        return lines

    def _fit_font(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        base_size: int,
        bold: bool,
        max_w: int,
        max_lines: int,
        min_size: int = 22,
    ):
        """Shrink font until text fits within max_lines at max_w."""
        size = base_size
        while size >= min_size:
            font = self._try_load_font(size, bold=bold)
            lines = self._wrap(draw, text, font, max_w, max_lines=None)
            if len(lines) <= max_lines:
                # Also ensure each line fits (very long tokens)
                if all(draw.textlength(line, font=font) <= max_w for line in lines):
                    return font, self._wrap(draw, text, font, max_w, max_lines)
            size -= 2
        font = self._try_load_font(min_size, bold=bold)
        return font, self._wrap(draw, text, font, max_w, max_lines)

    def _new_canvas(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        d = self.design
        img = Image.new("RGB", (d.width, d.height), d.bg)
        draw = ImageDraw.Draw(img)
        # Subtle top gradient band
        for i in range(180):
            ratio = i / 180
            color = tuple(
                int(d.bg[c] + (d.bg_accent[c] - d.bg[c]) * (1 - ratio))
                for c in range(3)
            )
            draw.line([(0, i), (d.width, i)], fill=color)
        # Accent rail
        draw.rectangle([(0, 0), (8, d.height)], fill=d.accent)
        return img, draw

    def _draw_brand_header(
        self,
        draw: ImageDraw.ImageDraw,
        y: int,
        date_text: str,
        risk_level: str,
    ) -> int:
        d = self.design
        x = d.margin_x
        draw.text((x, y), d.brand_name, font=self.fonts["brand"], fill=d.accent)
        y += 52
        draw.text((x, y), d.brand_tagline, font=self.fonts["small"], fill=d.muted)
        y += 36
        draw.text((x, y), date_text, font=self.fonts["date"], fill=d.white)
        y += 48

        risk_color = d.risk_colors.get(risk_level, d.risk_elevated)
        # Render label without emoji glyphs (more reliable across font sets)
        risk_label = risk_level.split(maxsplit=1)[-1] if risk_level else "Elevated"
        label = f"  {risk_label.upper()}  "
        bw = int(draw.textlength(label, font=self.fonts["risk"]) + 56)
        bh = 48
        draw.rounded_rectangle(
            [(x, y), (x + bw, y + bh)],
            radius=10,
            fill=tuple(c // 5 for c in risk_color),
            outline=risk_color,
            width=2,
        )
        draw.ellipse((x + 14, y + 14, x + 34, y + 34), fill=risk_color)
        draw.text((x + 42, y + 10), risk_label.upper(), font=self.fonts["risk"], fill=risk_color)
        return y + bh + d.content_gap

    def render_all(self, briefing: StoryBriefing, output_dir: Path) -> list[Path]:
        """
        Render three Story images into output_dir.
        Returns paths in publish order: overview, developments, singapore.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            paths = [
                self._save(self.render_overview(briefing), output_dir / "story_01_overview.png"),
                self._save(
                    self.render_developments(briefing),
                    output_dir / "story_02_developments.png",
                ),
                self._save(
                    self.render_singapore(briefing),
                    output_dir / "story_03_singapore.png",
                ),
            ]
            for path in paths:
                log.info("Rendered story image: %s", path)
            return paths
        except Exception as exc:
            log.error("Story rendering failed: %s", str(exc))
            raise StoryRenderError(str(exc)) from exc

    def _save(self, img: Image.Image, path: Path) -> Path:
        img.save(path, format="PNG", optimize=True)
        return path

    def render_overview(self, briefing: StoryBriefing) -> Image.Image:
        """Story 1 — daily overview."""
        d = self.design
        img, draw = self._new_canvas()
        y = d.content_top
        y = self._draw_brand_header(draw, y, briefing.brief_date, briefing.risk_level)

        draw.rectangle([(d.margin_x, y), (d.width - d.margin_x, y + 2)], fill=d.divider)
        y += d.content_gap

        headline_font, h_lines = self._fit_font(
            draw,
            briefing.headline,
            d.font_headline,
            bold=True,
            max_w=d.content_width,
            max_lines=d.max_headline_lines,
            min_size=32,
        )
        for line in h_lines:
            draw.text((d.margin_x, y), line, font=headline_font, fill=d.white)
            y += int(headline_font.size * 1.25) if hasattr(headline_font, "size") else 64
        y += d.content_gap

        overview_font, o_lines = self._fit_font(
            draw,
            briefing.overview,
            d.font_overview,
            bold=False,
            max_w=d.content_width,
            max_lines=d.max_overview_lines,
            min_size=24,
        )
        for line in o_lines:
            # Stay within bottom safe zone
            line_h = int(getattr(overview_font, "size", 34) * 1.35)
            if y + line_h > d.content_bottom:
                break
            draw.text((d.margin_x, y), line, font=overview_font, fill=d.muted)
            y += line_h

        self._draw_footer_mark(draw)
        return img

    def render_developments(self, briefing: StoryBriefing) -> Image.Image:
        """Story 2 — top developments (up to three)."""
        d = self.design
        img, draw = self._new_canvas()
        y = d.content_top

        draw.text((d.margin_x, y), d.brand_name, font=self.fonts["brand"], fill=d.accent)
        y += 52
        draw.text((d.margin_x, y), "TOP DEVELOPMENTS", font=self.fonts["section"], fill=d.white)
        y += 40
        draw.text((d.margin_x, y), briefing.brief_date, font=self.fonts["date"], fill=d.muted)
        y += 50
        draw.rectangle([(d.margin_x, y), (d.width - d.margin_x, y + 2)], fill=d.divider)
        y += d.content_gap + 8

        if not briefing.developments:
            draw.text(
                (d.margin_x, y),
                "No major developments selected today.",
                font=self.fonts["dev_body"],
                fill=d.muted,
            )
            self._draw_footer_mark(draw)
            return img

        available = d.content_bottom - y
        slot = available // max(len(briefing.developments), 1)

        for dev in briefing.developments:
            if y + 80 > d.content_bottom:
                break
            block_bottom = min(y + slot - 16, d.content_bottom)
            # Panel
            draw.rounded_rectangle(
                [(d.margin_x, y), (d.width - d.margin_x, block_bottom)],
                radius=18,
                fill=d.panel,
                outline=d.divider,
                width=1,
            )
            inner_x = d.margin_x + 28
            cy = y + 28

            num_color = d.accent
            draw.text(
                (inner_x, cy),
                dev.number,
                font=self.fonts["dev_number"],
                fill=num_color,
            )
            cy += 48

            title_font, t_lines = self._fit_font(
                draw,
                dev.title,
                d.font_dev_title,
                bold=True,
                max_w=d.content_width - 56,
                max_lines=2,
                min_size=26,
            )
            for line in t_lines:
                draw.text((inner_x, cy), line, font=title_font, fill=d.white)
                cy += int(getattr(title_font, "size", 40) * 1.2)

            cy += 12
            body_font, b_lines = self._fit_font(
                draw,
                dev.summary,
                d.font_dev_body,
                bold=False,
                max_w=d.content_width - 56,
                max_lines=d.max_dev_summary_lines,
                min_size=22,
            )
            for line in b_lines:
                if cy + 30 > block_bottom - 20:
                    break
                draw.text((inner_x, cy), line, font=body_font, fill=d.muted)
                cy += int(getattr(body_font, "size", 30) * 1.3)

            y = block_bottom + 20

        self._draw_footer_mark(draw)
        return img

    def render_singapore(self, briefing: StoryBriefing) -> Image.Image:
        """Story 3 — Singapore impact + watch next."""
        d = self.design
        img, draw = self._new_canvas()
        y = d.content_top

        draw.text((d.margin_x, y), d.brand_name, font=self.fonts["brand"], fill=d.accent)
        y += 52
        draw.text(
            (d.margin_x, y),
            "SG POSTURE · MINDEF",
            font=self.fonts["section"],
            fill=d.white,
        )
        y += 40
        draw.text((d.margin_x, y), briefing.brief_date, font=self.fonts["date"], fill=d.muted)
        y += 50
        draw.rectangle([(d.margin_x, y), (d.width - d.margin_x, y + 2)], fill=d.divider)
        y += d.content_gap

        for impact in briefing.singapore_impacts:
            if y + 120 > d.content_bottom - 220:
                break
            level_color = d.risk_colors.get(impact.level, d.risk_elevated)
            draw.rounded_rectangle(
                [(d.margin_x, y), (d.width - d.margin_x, y + 150)],
                radius=16,
                fill=d.panel,
                outline=d.divider,
            )
            # Level accent bar
            draw.rectangle(
                [(d.margin_x, y + 16), (d.margin_x + 6, y + 134)],
                fill=level_color,
            )
            ix = d.margin_x + 28
            draw.text((ix, y + 22), impact.area.upper(), font=self.fonts["impact_area"], fill=d.white)
            badge = impact.level.upper()
            draw.text((ix, y + 64), badge, font=self.fonts["small"], fill=level_color)

            expl_font, e_lines = self._fit_font(
                draw,
                impact.explanation,
                d.font_impact_body,
                bold=False,
                max_w=d.content_width - 56,
                max_lines=d.max_impact_lines,
                min_size=20,
            )
            ey = y + 96
            for line in e_lines:
                draw.text((ix, ey), line, font=expl_font, fill=d.muted)
                ey += int(getattr(expl_font, "size", 28) * 1.25)
            y += 170

        # Watch Next block — pinned above bottom safe zone
        watch_top = min(y + 10, d.content_bottom - 200)
        draw.rounded_rectangle(
            [(d.margin_x, watch_top), (d.width - d.margin_x, d.content_bottom - 20)],
            radius=16,
            fill=d.bg_accent,
            outline=d.accent,
            width=2,
        )
        draw.text(
            (d.margin_x + 28, watch_top + 24),
            "WATCH NEXT",
            font=self.fonts["section"],
            fill=d.accent,
        )
        watch_font, w_lines = self._fit_font(
            draw,
            briefing.watch_next,
            d.font_watch,
            bold=False,
            max_w=d.content_width - 56,
            max_lines=d.max_watch_lines,
            min_size=22,
        )
        wy = watch_top + 70
        for line in w_lines:
            draw.text((d.margin_x + 28, wy), line, font=watch_font, fill=d.white)
            wy += int(getattr(watch_font, "size", 30) * 1.3)

        self._draw_footer_mark(draw)
        return img

    def _draw_footer_mark(self, draw: ImageDraw.ImageDraw) -> None:
        """Small brand mark inside the content band, above the bottom safe zone."""
        d = self.design
        label = "SENTINEL · Singapore lens"
        y = d.content_bottom - 36
        draw.text((d.margin_x, y), label, font=self.fonts["small"], fill=d.muted)
