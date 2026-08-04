"""Tests for Story briefing validation, length limits, and Singapore dates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from analysts.story_brief import (
    StoryBriefValidationError,
    singapore_brief_date,
    singapore_date_folder,
    validate_story_briefing,
    word_count,
)


def test_valid_fixture_passes(sample_briefing_dict):
    briefing = validate_story_briefing(sample_briefing_dict)
    assert briefing.risk_level == "🟡 Elevated"
    assert len(briefing.developments) == 3
    assert briefing.developments[0].number == "01"


def test_rejects_malformed_non_object():
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing("not-json-object")  # type: ignore[arg-type]


def test_rejects_bad_risk_level(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["risk_level"] = "💜 Extreme"
    with pytest.raises(StoryBriefValidationError) as exc:
        validate_story_briefing(data)
    assert any("risk_level" in e for e in exc.value.errors)


def test_enforces_title_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"][0]["title"] = "one two three four five six seven"
    with pytest.raises(StoryBriefValidationError) as exc:
        validate_story_briefing(data)
    assert any("six words" in e.lower() or "title" in e for e in exc.value.errors)


def test_enforces_impact_explanation_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["singapore_impacts"][0]["explanation"] = " ".join(["word"] * 17)
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_impact_carries_so_what(sample_briefing_dict):
    briefing = validate_story_briefing(sample_briefing_dict)
    assert all(i.so_what for i in briefing.singapore_impacts)


def test_missing_impact_so_what_is_rejected(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    del data["singapore_impacts"][0]["so_what"]
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_enforces_impact_so_what_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["singapore_impacts"][0]["so_what"] = " ".join(["word"] * 15)
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_enforces_telegram_summary_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["telegram_summary"] = " ".join(["word"] * 36)
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_rejects_more_than_three_developments(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"].append({
        "number": "04",
        "title": "Fourth item here",
        "what_changed": "Something else happened today",
        "why_it_matters": "It should be rejected by the cap",
        "signal": "Reported",
    })
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_allows_fewer_than_three_developments(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"] = data["developments"][:1]
    briefing = validate_story_briefing(data)
    assert len(briefing.developments) == 1


def test_rejects_unsupported_impact_focus(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["singapore_impacts"][0]["area"] = "Moon base logistics"
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_accepts_posture_and_mindef_focuses(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["singapore_impacts"] = [
        {
            "area": "Geopolitical posture",
            "level": "High",
            "explanation": "Alliance signalling tightens Singapore's balancing room",
            "so_what": "Reaffirm neutrality with both major partners",
        },
        {
            "area": "MINDEF next steps",
            "level": "Elevated",
            "explanation": "Task MINDEF to refresh SLOC contingency drills",
            "so_what": "Schedule a maritime readiness review this quarter",
        },
    ]
    briefing = validate_story_briefing(data)
    assert briefing.singapore_impacts[0].area == "Geopolitical posture"
    assert briefing.singapore_impacts[1].area == "MINDEF next steps"


def test_ignores_invented_fields(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["secret_field"] = "should be ignored"
    briefing = validate_story_briefing(data)
    assert not hasattr(briefing, "secret_field")
    dumped = briefing.model_dump()
    assert "secret_field" not in dumped


def test_normalises_risk_aliases(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["risk_level"] = "Critical"
    briefing = validate_story_briefing(data)
    assert briefing.risk_level == "🔴 Critical"


def test_word_count_helper():
    assert word_count("one two  three") == 3
    assert word_count("  ") == 0


def test_singapore_brief_date_format():
    dt = datetime(2026, 8, 3, 1, 0, tzinfo=ZoneInfo("UTC"))  # 09:00 SGT
    assert singapore_brief_date(dt) == "03 Aug 2026"


def test_singapore_date_folder_conversion():
    # 2026-08-02 20:00 UTC == 2026-08-03 04:00 SGT
    dt = datetime(2026, 8, 2, 20, 0, tzinfo=ZoneInfo("UTC"))
    assert singapore_date_folder(dt) == "2026-08-03"


def test_requires_two_to_three_singapore_impacts(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["singapore_impacts"] = data["singapore_impacts"][:1]
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


# ── Enriched developments (what changed / why it matters / signal) ────────────

def test_development_carries_enriched_fields(sample_briefing_dict):
    briefing = validate_story_briefing(sample_briefing_dict)
    dev = briefing.developments[0]
    assert dev.what_changed
    assert dev.why_it_matters
    assert dev.signal in {"Confirmed", "Reported", "Assessed"}


def test_enforces_what_changed_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"][0]["what_changed"] = " ".join(["word"] * 25)
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_enforces_why_it_matters_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"][0]["why_it_matters"] = " ".join(["word"] * 25)
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_missing_what_changed_is_rejected(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    del data["developments"][0]["what_changed"]
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_signal_normalises_aliases(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"][0]["signal"] = "official"
    briefing = validate_story_briefing(data)
    assert briefing.developments[0].signal == "Confirmed"


def test_signal_defaults_when_blank(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"][0]["signal"] = ""
    briefing = validate_story_briefing(data)
    assert briefing.developments[0].signal == "Reported"


def test_rejects_unsupported_signal(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["developments"][0]["signal"] = "fabricated"
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


# ── Theory lens (Story 4) ─────────────────────────────────────────────────────

def test_theory_lens_present_and_valid(sample_briefing_dict):
    briefing = validate_story_briefing(sample_briefing_dict)
    assert briefing.theory_lens.theory
    assert briefing.theory_lens.application
    assert briefing.theory_lens.takeaway


def test_missing_theory_lens_is_rejected(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    del data["theory_lens"]
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_theory_application_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["theory_lens"]["application"] = " ".join(["word"] * 49)
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_theory_name_word_limit(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["theory_lens"]["theory"] = "one two three four five six seven"
    with pytest.raises(StoryBriefValidationError):
        validate_story_briefing(data)


def test_theory_tradition_optional(sample_briefing_dict):
    data = deepcopy(sample_briefing_dict)
    data["theory_lens"]["tradition"] = ""
    briefing = validate_story_briefing(data)
    assert briefing.theory_lens.tradition == ""
