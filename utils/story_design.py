"""
SENTINEL — Instagram Story Design Configuration
Colours, typography, spacing and safe-zone constants.
Keep visual tokens here so business logic stays design-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryDesign:
    """Visual design tokens for 1080×1920 Instagram Stories."""

    # Canvas
    width: int = 1080
    height: int = 1920

    # Instagram UI safe zones (content must stay between these)
    safe_top: int = 280
    safe_bottom: int = 250  # pixels reserved at bottom

    # Margins inside the safe content band
    margin_x: int = 72
    content_gap: int = 28
    footer_reserve: int = 46  # room for the brand footer mark

    # Branding
    brand_name: str = "SENTINEL"
    brand_tagline: str = "DAILY INTEL BRIEF"

    # Palette — dark intelligence dashboard
    bg: tuple[int, int, int] = (10, 14, 20)
    bg_accent: tuple[int, int, int] = (16, 22, 32)
    panel: tuple[int, int, int] = (22, 28, 38)
    accent: tuple[int, int, int] = (0, 180, 216)
    white: tuple[int, int, int] = (232, 238, 244)
    muted: tuple[int, int, int] = (130, 140, 155)
    divider: tuple[int, int, int] = (42, 50, 62)

    # Risk colours
    risk_stable: tuple[int, int, int] = (63, 185, 80)
    risk_elevated: tuple[int, int, int] = (255, 185, 0)
    risk_high: tuple[int, int, int] = (255, 140, 0)
    risk_critical: tuple[int, int, int] = (248, 81, 73)

    # Typography sizes (px)
    font_brand: int = 42
    font_date: int = 28
    font_risk: int = 30
    font_headline: int = 56
    font_overview: int = 34
    font_section: int = 26
    font_dev_number: int = 34
    font_dev_title: int = 38
    font_dev_body: int = 28
    font_label: int = 22
    font_impact_area: int = 32
    font_impact_body: int = 28
    font_watch: int = 30
    font_theory_name: int = 54
    font_theory_body: int = 30
    font_small: int = 22

    # Text overflow
    max_headline_lines: int = 3
    max_overview_lines: int = 6
    max_dev_changed_lines: int = 2
    max_dev_why_lines: int = 2
    max_impact_lines: int = 2
    max_watch_lines: int = 3
    max_theory_lines: int = 7
    max_theory_takeaway_lines: int = 3
    ellipsis: str = "…"

    # Confidence-signal accent colours (Story 2)
    signal_confirmed: tuple[int, int, int] = (63, 185, 80)
    signal_reported: tuple[int, int, int] = (0, 180, 216)
    signal_assessed: tuple[int, int, int] = (255, 185, 0)

    # Font search paths (macOS + Linux CI)
    font_regular_paths: tuple[tuple[str, int | None], ...] = (
        ("/System/Library/Fonts/Helvetica.ttc", 0),
        ("/System/Library/Fonts/SFNSText.ttf", None),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", None),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", None),
    )
    font_bold_paths: tuple[tuple[str, int | None], ...] = (
        ("/System/Library/Fonts/Helvetica.ttc", 1),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", None),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", None),
    )

    @property
    def risk_colors(self) -> dict[str, tuple[int, int, int]]:
        return {
            "🟢 Stable": self.risk_stable,
            "🟡 Elevated": self.risk_elevated,
            "🟠 High": self.risk_high,
            "🔴 Critical": self.risk_critical,
            "Stable": self.risk_stable,
            "Elevated": self.risk_elevated,
            "High": self.risk_high,
            "Critical": self.risk_critical,
        }

    @property
    def signal_colors(self) -> dict[str, tuple[int, int, int]]:
        return {
            "Confirmed": self.signal_confirmed,
            "Reported": self.signal_reported,
            "Assessed": self.signal_assessed,
        }

    @property
    def content_top(self) -> int:
        return self.safe_top

    @property
    def content_bottom(self) -> int:
        return self.height - self.safe_bottom

    @property
    def content_width(self) -> int:
        return self.width - (2 * self.margin_x)


DEFAULT_STORY_DESIGN = StoryDesign()
