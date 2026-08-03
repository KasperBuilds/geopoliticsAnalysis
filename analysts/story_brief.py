"""
SENTINEL — Instagram Story Brief Composer
Produces a validated, Story-ready JSON brief from analyst synthesised intel.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from analysts.base_analyst import AnalystBrief
from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL, TIMEZONE
from utils.logger import get_logger

log = get_logger("story_brief")

ALLOWED_RISK_LEVELS = {
    "🟢 Stable",
    "🟡 Elevated",
    "🟠 High",
    "🔴 Critical",
}

ALLOWED_IMPACT_LEVELS = {"Stable", "Elevated", "High", "Critical"}

# Story 3 focuses on Singapore's geopolitical posture and MINDEF actionability
ALLOWED_IMPACT_FOCUSES = {
    "Geopolitical posture",
    "MINDEF next steps",
    "SAF readiness",
    "Defence diplomacy",
}

MAX_DEVELOPMENTS = 3
MAX_TITLE_WORDS = 6
MAX_IMPACT_EXPLANATION_WORDS = 16
MAX_TELEGRAM_SUMMARY_WORDS = 35
MIN_SINGAPORE_IMPACTS = 2
MAX_SINGAPORE_IMPACTS = 3
LLM_MAX_RETRIES = 2


def word_count(text: str) -> int:
    """Count whitespace-separated words, ignoring empty tokens."""
    return len([w for w in text.strip().split() if w])


def singapore_brief_date(dt: datetime | None = None) -> str:
    """Return a briefing date string in Singapore time, e.g. '03 Aug 2026'."""
    when = dt or datetime.now(ZoneInfo(TIMEZONE))
    if when.tzinfo is None:
        when = when.replace(tzinfo=ZoneInfo(TIMEZONE))
    else:
        when = when.astimezone(ZoneInfo(TIMEZONE))
    return when.strftime("%d %b %Y")


def singapore_date_folder(dt: datetime | None = None) -> str:
    """Return YYYY-MM-DD in Singapore time for archive folders."""
    when = dt or datetime.now(ZoneInfo(TIMEZONE))
    if when.tzinfo is None:
        when = when.replace(tzinfo=ZoneInfo(TIMEZONE))
    else:
        when = when.astimezone(ZoneInfo(TIMEZONE))
    return when.strftime("%Y-%m-%d")


class StoryDevelopment(BaseModel):
    number: str
    title: str
    summary: str

    @field_validator("number")
    @classmethod
    def validate_number(cls, value: str) -> str:
        value = value.strip()
        if value not in {"01", "02", "03"}:
            raise ValueError("development number must be 01, 02, or 03")
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("development title is required")
        if word_count(value) > MAX_TITLE_WORDS:
            raise ValueError(f"development title exceeds {MAX_TITLE_WORDS} words")
        return value

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("development summary is required")
        return value


class SingaporeImpact(BaseModel):
    area: str
    level: str
    explanation: str

    @field_validator("area")
    @classmethod
    def validate_area(cls, value: str) -> str:
        value = value.strip()
        # Accept case-insensitive match against the posture / MINDEF catalogue
        for allowed in ALLOWED_IMPACT_FOCUSES:
            if value.lower() == allowed.lower():
                return allowed
        raise ValueError(f"unsupported singapore impact focus: {value}")

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        cleaned = value.strip()
        # Strip leading emoji if the model includes one
        cleaned = re.sub(r"^[🟢🟡🟠🔴]\s*", "", cleaned).strip()
        for allowed in ALLOWED_IMPACT_LEVELS:
            if cleaned.lower() == allowed.lower():
                return allowed
        raise ValueError(f"unsupported impact level: {value}")

    @field_validator("explanation")
    @classmethod
    def validate_explanation(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("singapore impact explanation is required")
        if word_count(value) > MAX_IMPACT_EXPLANATION_WORDS:
            raise ValueError(
                f"singapore impact explanation exceeds {MAX_IMPACT_EXPLANATION_WORDS} words"
            )
        return value


class StorySource(BaseModel):
    title: str
    publisher: str
    url: str

    @field_validator("title", "publisher", "url")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source fields must be non-empty")
        return value


class StoryBriefing(BaseModel):
    """Validated Instagram Story briefing payload."""

    brief_date: str
    risk_level: str
    headline: str
    overview: str
    developments: list[StoryDevelopment] = Field(default_factory=list)
    singapore_impacts: list[SingaporeImpact] = Field(default_factory=list)
    watch_next: str
    telegram_summary: str
    sources: list[StorySource] = Field(default_factory=list)

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, value: str) -> str:
        value = value.strip()
        # Normalise common model variants
        aliases = {
            "stable": "🟢 Stable",
            "elevated": "🟡 Elevated",
            "high": "🟠 High",
            "critical": "🔴 Critical",
            "routine": "🟢 Stable",
            "🟢 stable": "🟢 Stable",
            "🟡 elevated": "🟡 Elevated",
            "🟠 high": "🟠 High",
            "🔴 critical": "🔴 Critical",
        }
        normalised = aliases.get(value.lower(), value)
        if normalised not in ALLOWED_RISK_LEVELS:
            raise ValueError(f"unsupported risk_level: {value}")
        return normalised

    @field_validator("headline", "overview", "watch_next")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required text field is empty")
        return value

    @field_validator("telegram_summary")
    @classmethod
    def validate_telegram_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("telegram_summary is required")
        if word_count(value) > MAX_TELEGRAM_SUMMARY_WORDS:
            raise ValueError(
                f"telegram_summary exceeds {MAX_TELEGRAM_SUMMARY_WORDS} words"
            )
        return value

    @model_validator(mode="after")
    def validate_collections(self) -> StoryBriefing:
        if len(self.developments) > MAX_DEVELOPMENTS:
            raise ValueError(f"at most {MAX_DEVELOPMENTS} developments allowed")
        if not (MIN_SINGAPORE_IMPACTS <= len(self.singapore_impacts) <= MAX_SINGAPORE_IMPACTS):
            raise ValueError(
                f"singapore_impacts must contain {MIN_SINGAPORE_IMPACTS}-{MAX_SINGAPORE_IMPACTS} items"
            )
        # Enforce sequential numbering matching list order
        for idx, dev in enumerate(self.developments, start=1):
            expected = f"{idx:02d}"
            if dev.number != expected:
                raise ValueError(
                    f"development number mismatch: expected {expected}, got {dev.number}"
                )
        if not self.sources:
            raise ValueError("at least one source is required")
        return self


class StoryBriefValidationError(Exception):
    """Raised when Story briefing JSON cannot be validated."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


def validate_story_briefing(data: dict[str, Any] | StoryBriefing) -> StoryBriefing:
    """
    Validate a story briefing dict against the formal schema.
    Rejects malformed output and unsupported fields via Pydantic.
    """
    if isinstance(data, StoryBriefing):
        return data
    if not isinstance(data, dict):
        raise StoryBriefValidationError("Story briefing payload must be a JSON object")

    # Strip unknown top-level keys so invented fields are not rendered
    allowed_keys = set(StoryBriefing.model_fields.keys())
    unknown = sorted(set(data.keys()) - allowed_keys)
    if unknown:
        log.warning("Ignoring unsupported story briefing fields: %s", ", ".join(unknown))
    cleaned = {k: v for k, v in data.items() if k in allowed_keys}

    try:
        return StoryBriefing.model_validate(cleaned)
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            errors.append(f"{loc}: {err.get('msg', 'invalid')}")
        log.error("Story briefing validation failed: %s", "; ".join(errors))
        raise StoryBriefValidationError("Story briefing validation failed", errors) from exc


def _compile_analyst_context(briefs: list[AnalystBrief]) -> tuple[str, list[dict[str, str]]]:
    """Flatten analyst briefs into LLM context and a source catalogue."""
    lines: list[str] = []
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    article_n = 1

    for brief in briefs:
        lines.append(f"ANALYST: {brief.analyst_role} | Urgency: {brief.overall_urgency}")
        lines.append(f"Headline: {brief.headline}")
        lines.append(f"Summary: {brief.executive_summary}")
        for i, dev in enumerate(brief.key_developments, 1):
            lines.append(
                f"  Dev {i}: {dev.headline} [{dev.urgency}] "
                f"why={dev.why}; sg={dev.sg_impact}"
            )
            lines.append(f"    Analysis: {dev.analysis}")
            for src, url in zip(dev.sources, dev.source_urls or [""] * len(dev.sources)):
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    sources.append({
                        "n": str(article_n),
                        "title": dev.headline,
                        "publisher": src,
                        "url": url,
                    })
                    lines.append(f"    [SRC {article_n}] {src} — {url}")
                    article_n += 1
                elif src and not url:
                    sources.append({
                        "n": str(article_n),
                        "title": dev.headline,
                        "publisher": src,
                        "url": f"unavailable://{src}",
                    })
                    article_n += 1
        for impl in brief.singapore_implications:
            lines.append(f"  SG implication: {impl}")
        for item in brief.watchlist:
            lines.append(f"  Watch: {item}")
        lines.append("")

    return "\n".join(lines), sources


def _build_prompt(context: str, sources: list[dict[str, str]], brief_date: str) -> str:
    source_block = "\n".join(
        f"[{s['n']}] {s['title']} | {s['publisher']} | {s['url']}" for s in sources
    ) or "(no resolved URLs — cite publisher names only)"

    focuses = ", ".join(sorted(ALLOWED_IMPACT_FOCUSES))
    return f"""Compose today's SENTINEL Instagram Story briefing from the synthesised intelligence below.

ACCURACY RULES (mandatory):
1. Use ONLY the supplied intelligence. Do not invent events, actors, or numbers.
2. Merge duplicate reporting about the same event into one development.
3. Distinguish confirmed facts from reports or inference (e.g. "reported", "assessed").
4. Do not exaggerate risk. Prefer the lower level when evidence is thin.
5. Prioritise Singapore relevance when selecting developments.
6. Select at most three main developments. Use fewer if fewer credible items exist.
7. singapore_impacts must focus on Singapore's geopolitical posture and/or MINDEF implications.
   Allowed "area" values only: {focuses}
   - "Geopolitical posture": how today's events affect Singapore's balancing, alliances, or diplomatic stance
   - "MINDEF next steps": concrete near-term actions or reviews for MINDEF/SAF
   - "SAF readiness": force posture, training, readiness, or capability implications
   - "Defence diplomacy": defence partnerships, exercises, or mil-to-mil signalling
   Prefer at least one "Geopolitical posture" and one "MINDEF next steps" when both are supportable.
8. Every source entry must correspond to material in the feed.

BRIEF DATE (Singapore time): {brief_date}

SYNTHESISED INTELLIGENCE:
{context}

AVAILABLE SOURCES:
{source_block}

Return ONLY valid JSON matching this schema exactly:
{{
  "brief_date": "{brief_date}",
  "risk_level": "🟡 Elevated",
  "headline": "Concise overall headline",
  "overview": "Two or three sentence overview of the strategic picture.",
  "developments": [
    {{
      "number": "01",
      "title": "Maximum six words",
      "summary": "What changed and why it matters"
    }}
  ],
  "singapore_impacts": [
    {{
      "area": "Geopolitical posture",
      "level": "High",
      "explanation": "How this shifts Singapore's strategic stance"
    }},
    {{
      "area": "MINDEF next steps",
      "level": "Elevated",
      "explanation": "Concrete near-term MINDEF or SAF action"
    }}
  ],
  "watch_next": "One observable MINDEF-, SAF-, or diplomacy-relevant indicator",
  "telegram_summary": "Maximum 35 words",
  "sources": [
    {{
      "title": "Article title",
      "publisher": "Publisher",
      "url": "Original URL"
    }}
  ]
}}

CONSTRAINTS:
- risk_level must be exactly one of: 🟢 Stable | 🟡 Elevated | 🟠 High | 🔴 Critical
- developments: 0–3 items, numbers "01","02","03" in order, titles ≤6 words
- singapore_impacts: 2–3 items; area from the allowed posture/MINDEF list; level one of Stable|Elevated|High|Critical; explanation ≤16 words and action-oriented
- watch_next should be something MINDEF/MFA/SAF can observe next
- telegram_summary ≤35 words
- Do not include any fields outside the schema
"""


def _build_correction_prompt(errors: list[str], previous_json: str) -> str:
    error_list = "\n".join(f"- {e}" for e in errors)
    return f"""Your previous JSON failed validation. Fix ALL errors and return corrected JSON only.

VALIDATION ERRORS:
{error_list}

PREVIOUS OUTPUT:
{previous_json}

Return a single corrected JSON object matching the required schema. No commentary.
"""


class StoryBriefComposer:
    """LLM-backed composer that produces a validated StoryBriefing."""

    def __init__(self):
        self.client = (
            OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
            if OPENROUTER_API_KEY
            else None
        )

    def compose(self, briefs: list[AnalystBrief]) -> StoryBriefing:
        """Compose and validate a Story briefing from analyst briefs."""
        if not briefs:
            raise StoryBriefValidationError("No analyst briefs available for story composition")

        brief_date = singapore_brief_date()
        context, sources = _compile_analyst_context(briefs)

        if not self.client:
            log.warning("No OpenRouter API key — building story brief from analyst data")
            return self._fallback_brief(briefs, brief_date, sources)

        prompt = _build_prompt(context, sources, brief_date)
        system = (
            "You are SENTINEL Story Desk — a precise intelligence editor producing "
            "Instagram Story briefings for Singapore-focused defence and geoeconomics. "
            "Output strict JSON only. Never invent facts beyond the supplied feed."
        )

        last_errors: list[str] = []
        last_raw = ""

        for attempt in range(LLM_MAX_RETRIES + 1):
            try:
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ]
                if attempt > 0:
                    messages.append({
                        "role": "user",
                        "content": _build_correction_prompt(last_errors, last_raw),
                    })

                response = self.client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.3,
                    max_tokens=2500,
                )
                last_raw = response.choices[0].message.content or ""
                data = json.loads(last_raw)
                # Enforce Singapore date from our clock, not the model
                data["brief_date"] = brief_date
                briefing = validate_story_briefing(data)
                log.info(
                    "Story brief composed: risk=%s developments=%d",
                    briefing.risk_level,
                    len(briefing.developments),
                )
                return briefing
            except (json.JSONDecodeError, StoryBriefValidationError, ValidationError) as exc:
                if isinstance(exc, StoryBriefValidationError):
                    last_errors = exc.errors
                elif isinstance(exc, ValidationError):
                    last_errors = [e["msg"] for e in exc.errors()]
                else:
                    last_errors = [f"Invalid JSON: {exc}"]
                log.warning(
                    "Story brief attempt %d/%d failed validation: %s",
                    attempt + 1,
                    LLM_MAX_RETRIES + 1,
                    "; ".join(last_errors),
                )

        raise StoryBriefValidationError(
            "Story briefing failed validation after retries",
            last_errors,
        )

    def _fallback_brief(
        self,
        briefs: list[AnalystBrief],
        brief_date: str,
        sources: list[dict[str, str]],
    ) -> StoryBriefing:
        """Deterministic fallback when the LLM is unavailable (tests / offline)."""
        urgency_map = {
            "CRITICAL": "🔴 Critical",
            "ELEVATED": "🟡 Elevated",
            "ROUTINE": "🟢 Stable",
        }
        urgency_order = {"CRITICAL": 3, "ELEVATED": 2, "ROUTINE": 1}
        top = max(briefs, key=lambda b: urgency_order.get(b.overall_urgency, 0))

        developments: list[StoryDevelopment] = []
        for brief in briefs:
            for dev in brief.key_developments:
                if len(developments) >= MAX_DEVELOPMENTS:
                    break
                title_words = dev.headline.split()[:MAX_TITLE_WORDS]
                developments.append(
                    StoryDevelopment(
                        number=f"{len(developments) + 1:02d}",
                        title=" ".join(title_words) or "Key development",
                        summary=(dev.analysis or dev.why or dev.headline)[:280],
                    )
                )
            if len(developments) >= MAX_DEVELOPMENTS:
                break

        impacts: list[SingaporeImpact] = []
        for brief in briefs:
            for impl in brief.singapore_implications:
                if len(impacts) >= MAX_SINGAPORE_IMPACTS:
                    break
                text = impl.lower()
                if any(k in text for k in ("mindef", "saf", "exercise", "readiness", "procure")):
                    area = "MINDEF next steps"
                elif any(k in text for k in ("diplomacy", "asean", "alliance", "partner", "mfa")):
                    area = "Defence diplomacy"
                elif any(k in text for k in ("force", "deploy", "patrol", "training")):
                    area = "SAF readiness"
                else:
                    area = "Geopolitical posture"
                # Alternate focus so Story 3 is not all one category
                if impacts and impacts[-1].area == area:
                    area = (
                        "MINDEF next steps"
                        if area != "MINDEF next steps"
                        else "Geopolitical posture"
                    )
                words = impl.split()[:MAX_IMPACT_EXPLANATION_WORDS]
                impacts.append(
                    SingaporeImpact(
                        area=area,
                        level="Elevated" if top.overall_urgency == "ELEVATED" else "Stable",
                        explanation=" ".join(words),
                    )
                )
            if len(impacts) >= MAX_SINGAPORE_IMPACTS:
                break

        while len(impacts) < MIN_SINGAPORE_IMPACTS:
            filler_area = (
                "MINDEF next steps"
                if not any(i.area == "MINDEF next steps" for i in impacts)
                else "Geopolitical posture"
            )
            impacts.append(
                SingaporeImpact(
                    area=filler_area,
                    level="Stable",
                    explanation=(
                        "Review force posture against regional signalling"
                        if filler_area == "MINDEF next steps"
                        else "Hold steady hedging stance pending clearer moves"
                    ),
                )
            )

        story_sources = [
            StorySource(
                title=s["title"],
                publisher=s["publisher"],
                url=s["url"],
            )
            for s in sources[:8]
        ]
        if not story_sources:
            story_sources = [
                StorySource(
                    title=top.headline,
                    publisher="SENTINEL sensors",
                    url="unavailable://sentinel",
                )
            ]

        watch = "Monitor official statements and force movements"
        for brief in briefs:
            if brief.watchlist:
                watch = brief.watchlist[0]
                break

        return validate_story_briefing({
            "brief_date": brief_date,
            "risk_level": urgency_map.get(top.overall_urgency, "🟢 Stable"),
            "headline": top.headline[:120],
            "overview": top.executive_summary or top.headline,
            "developments": [d.model_dump() for d in developments],
            "singapore_impacts": [i.model_dump() for i in impacts[:MAX_SINGAPORE_IMPACTS]],
            "watch_next": watch,
            "telegram_summary": " ".join((top.executive_summary or top.headline).split()[:35]),
            "sources": [s.model_dump() for s in story_sources],
        })
