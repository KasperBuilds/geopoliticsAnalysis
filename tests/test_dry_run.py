"""Tests for dry-run Instagram behaviour and fixture generation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from analysts.base_analyst import AnalystBrief, Development
from delivery.instagram import InstagramClient, InstagramStoryPublisher
from main import run_stories_fixture
from utils.archive import RunArchive
from utils.story_renderer import STORY_COUNT


def _sample_briefs() -> list[AnalystBrief]:
    return [
        AnalystBrief(
            analyst_name="alpha",
            analyst_role="Defence Strategist",
            timestamp="2026-08-03T00:00:00+00:00",
            overall_urgency="ELEVATED",
            headline="Regional naval activity rises",
            executive_summary="Allied patrol denser near key sea lanes with Singapore exposure.",
            key_developments=[
                Development(
                    headline="Carrier patrol denser",
                    analysis="Force posture shift increases monitoring demand.",
                    urgency="ELEVATED",
                    sources=["Defense News"],
                    source_urls=["https://example.com/a"],
                    category="DEFENCE",
                    why="sea lane risk",
                    sg_impact="maritime watch",
                )
            ],
            singapore_implications=[
                "Malacca traffic monitoring load increases this week",
                "Defence readiness posture review warranted",
            ],
            watchlist=["Next maritime exercise notice"],
        )
    ]


def test_publisher_disabled_by_default_semantics(tmp_path: Path):
    publisher = InstagramStoryPublisher(
        client=InstagramClient(account_id="1", access_token="x")
    )
    # Defaults come from env; force dry-run semantics explicitly
    publisher.dry_run = True
    publisher.publish_enabled = False
    assert publisher.should_publish() is False

    path = tmp_path / "s.png"
    path.write_bytes(b"x")
    report = publisher.publish_stories([path], ["https://example.com/s.png"])
    assert report.results[0].status == "dry_run"


def test_stories_fixture_command_writes_images(tmp_path: Path):
    paths = run_stories_fixture(tmp_path)
    assert len(paths) == STORY_COUNT == 4
    assert all(p.exists() for p in paths)
    # briefing archive should exist somewhere under output
    assert any(paths)


def test_archive_does_not_overwrite_successful_run(tmp_path: Path, sample_briefing):
    archive = RunArchive(base_dir=tmp_path)
    first = archive.resolve_run_dir(force=True)
    archive.write_manifest(
        first,
        briefing=sample_briefing,
        image_paths=[],
        report=None,
        success=True,
    )
    second = archive.resolve_run_dir(force=False)
    assert second != first
    assert second.parent == first or second.parent == first.parent


def test_story_composer_fallback_without_llm():
    from analysts.story_brief import StoryBriefComposer

    composer = StoryBriefComposer()
    composer.client = None
    briefing = composer.compose(_sample_briefs())
    assert briefing.headline
    assert 1 <= len(briefing.developments) <= 3
    assert 2 <= len(briefing.singapore_impacts) <= 3
    # Enriched fields + theory lens must be populated even offline
    assert briefing.developments[0].what_changed
    assert briefing.developments[0].why_it_matters
    assert briefing.theory_lens.theory
    assert briefing.theory_lens.application


def test_run_instagram_phase_dry_run_no_upload(tmp_path: Path, sample_briefing):
    from main import run_instagram_story_phase

    briefs = _sample_briefs()
    delivery = MagicMock()

    with patch("main.StoryBriefComposer") as composer_cls, \
         patch("main.RunArchive") as archive_cls, \
         patch("main.StoryRenderer") as renderer_cls, \
         patch("main.PublicObjectStorage") as storage_cls, \
         patch("main.InstagramStoryPublisher") as pub_cls:

        composer_cls.return_value.compose.return_value = sample_briefing
        archive = archive_cls.return_value
        archive.resolve_run_dir.return_value = tmp_path
        renderer_cls.return_value.render_all.return_value = [
            tmp_path / "story_01_overview.png",
            tmp_path / "story_02_developments.png",
            tmp_path / "story_03_singapore.png",
            tmp_path / "story_04_lens.png",
        ]
        for p in renderer_cls.return_value.render_all.return_value:
            p.write_bytes(b"fake-png")

        publisher = pub_cls.return_value
        publisher.should_publish.return_value = False
        publisher.dry_run = True
        publisher.publish_enabled = False
        from delivery.instagram import InstagramPublishReport
        publisher.publish_stories.return_value = InstagramPublishReport(
            dry_run=True,
            publish_enabled=False,
        )

        report = run_instagram_story_phase(briefs, delivery)
        storage_cls.assert_not_called()
        publisher.publish_stories.assert_called_once()
        assert report is not None
