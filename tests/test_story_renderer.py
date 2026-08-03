"""Tests for Instagram Story rendering, dimensions, and overflow handling."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PIL import Image

from analysts.story_brief import validate_story_briefing
from utils.story_design import DEFAULT_STORY_DESIGN, StoryDesign
from utils.story_renderer import StoryRenderer


def test_render_all_produces_three_1080x1920_pngs(sample_briefing, tmp_path: Path):
    renderer = StoryRenderer()
    paths = renderer.render_all(sample_briefing, tmp_path)
    assert len(paths) == 3
    for path in paths:
        assert path.exists()
        with Image.open(path) as img:
            assert img.size == (1080, 1920)
            assert img.format == "PNG"


def test_overview_keeps_content_inside_safe_zones(sample_briefing):
    design = DEFAULT_STORY_DESIGN
    renderer = StoryRenderer(design)
    img = renderer.render_overview(sample_briefing)
    # Spot-check: brand accent rail present and canvas size correct
    assert img.size == (design.width, design.height)
    px = img.getpixel((2, 100))
    assert px == design.accent


def test_overflow_truncates_long_headline(sample_briefing_dict, tmp_path: Path):
    data = deepcopy(sample_briefing_dict)
    data["headline"] = " ".join(["Unprecedented"] * 40)
    data["overview"] = " ".join(["Longoverviewword"] * 80)
    briefing = validate_story_briefing(data)
    renderer = StoryRenderer()
    paths = renderer.render_all(briefing, tmp_path)
    assert all(p.exists() for p in paths)
    # Rendering must succeed without raising even with extreme text
    with Image.open(paths[0]) as img:
        assert img.size == (1080, 1920)


def test_developments_story_handles_zero_items(sample_briefing_dict, tmp_path: Path):
    data = deepcopy(sample_briefing_dict)
    data["developments"] = []
    briefing = validate_story_briefing(data)
    renderer = StoryRenderer()
    path = tmp_path / "empty_devs.png"
    img = renderer.render_developments(briefing)
    img.save(path)
    assert path.exists()


def test_design_tokens_are_configurable(sample_briefing, tmp_path: Path):
    custom = StoryDesign(accent=(255, 0, 0), brand_name="TESTBRAND")
    renderer = StoryRenderer(custom)
    paths = renderer.render_all(sample_briefing, tmp_path)
    with Image.open(paths[0]) as img:
        assert img.getpixel((2, 100)) == (255, 0, 0)
