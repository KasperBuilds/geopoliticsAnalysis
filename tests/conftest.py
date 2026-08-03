"""Shared pytest fixtures for SENTINEL tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analysts.story_brief import StoryBriefing, validate_story_briefing

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_briefing_dict() -> dict:
    return json.loads((FIXTURE_DIR / "sample_story_brief.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_briefing(sample_briefing_dict) -> StoryBriefing:
    return validate_story_briefing(sample_briefing_dict)
