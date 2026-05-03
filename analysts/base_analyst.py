"""
SENTINEL — Base Analyst Agent
Abstract base class for PhD-level synthesis analysts.
Takes sensor reports, synthesises across domains, and produces strategic briefs.
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from openai import OpenAI
from pydantic import BaseModel

from config import OPENAI_API_KEY, OPENAI_MODEL
from sensors.base_sensor import SensorReport, IntelItem
from utils.dedup import DedupStore
from utils.logger import get_logger


# ── Pydantic Models ─────────────────────────────────────────

class Development(BaseModel):
    """A single key development with analysis."""
    headline: str
    analysis: str
    urgency: str  # CRITICAL, ELEVATED, ROUTINE
    sources: list[str] = []       # display names
    source_urls: list[str] = []   # full article URLs
    # TL;DR compact fields
    category: str = ""            # DEFENCE, GEOPOLITICS, or GEOECONOMICS
    why: str = ""                 # ultra-short why it matters (e.g. "high-tech warfare shift")
    sg_impact: str = ""           # ultra-short SG impact (e.g. "upgrade C4ISR")


class AnalystBrief(BaseModel):
    """The structured output of an analyst's synthesis."""
    analyst_name: str
    analyst_role: str
    timestamp: str
    overall_urgency: str  # CRITICAL, ELEVATED, ROUTINE
    headline: str
    executive_summary: str
    key_developments: list[Development] = []
    singapore_implications: list[str] = []
    watchlist: list[str] = []
    raw_text: str = ""  # Full formatted text for Telegram delivery


class BaseAnalyst(ABC):
    """
    Abstract PhD-level synthesis analyst.

    Takes multiple SensorReports, cross-references developments,
    identifies patterns, and produces a strategic brief with
    Singapore-specific implications.
    """

    def __init__(self):
        self.name = self._analyst_name()
        self.role = self._analyst_role()
        self.system_prompt = self._system_prompt()
        self.log = get_logger(f"analyst.{self.name}")
        self.client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

    @abstractmethod
    def _analyst_name(self) -> str:
        ...

    @abstractmethod
    def _analyst_role(self) -> str:
        ...

    @abstractmethod
    def _system_prompt(self) -> str:
        ...

    def _compile_sensor_inputs(self, reports: list[SensorReport]) -> tuple[str, dict[int, dict]]:
        """
        Format sensor reports into a structured input for the LLM.
        Returns (compiled_text, article_index) where article_index maps
        global article numbers to {source, url} for URL resolution.
        """
        compiled = ""
        article_index: dict[int, dict] = {}  # global_idx -> {source, url}
        global_idx = 1

        for report in reports:
            if not report.items:
                continue

            compiled += f"\n{'='*60}\n"
            compiled += f"SENSOR: {report.sensor_name.upper()} ({report.domain})\n"
            compiled += f"{'='*60}\n"

            for item in report.items:
                article_index[global_idx] = {
                    "source": item.source,
                    "url": item.url,
                }
                compiled += (
                    f"\n[ARTICLE {global_idx}] {item.headline}\n"
                    f"   Source: {item.source}\n"
                    f"   URL: {item.url}\n"
                    f"   Summary: {item.summary}\n"
                    f"   Entities: {', '.join(item.key_entities)}\n"
                )
                global_idx += 1

        text = compiled if compiled else "No significant intelligence items reported by sensors in this cycle."
        return text, article_index

    def analyse(self, reports: list[SensorReport]) -> AnalystBrief:
        """
        Synthesise sensor reports into a strategic analyst brief.
        This is where the PhD-level reasoning happens.
        """
        self.log.info("━━━ ANALYST %s ACTIVATED ━━━", self.name.upper())

        sensor_input, article_index = self._compile_sensor_inputs(reports)

        # Layer 3: Fetch narrative context to prevent buildup repetition
        dedup = DedupStore()
        narrative_context = dedup.format_narrative_context()
        if narrative_context:
            self.log.info("Injecting %d active narrative threads into analyst prompt",
                         len(dedup.get_active_narratives()))

        if not self.client:
            self.log.warning("No OpenAI API key — producing placeholder brief")
            return self._placeholder_brief(reports)

        # Build the narrative awareness block (empty string if no prior narratives)
        narrative_block = f"\n{narrative_context}\n" if narrative_context else ""

        prompt = f"""You have received the following intelligence items from your sensor network.
Your task is to synthesise these into a strategic brief.
{narrative_block}

CRITICAL INSTRUCTIONS:
1. Do NOT merely summarise each article. SYNTHESISE across sources to identify patterns, connections, and emerging trends.
2. Every development MUST include analysis of second-order implications — what does this MEAN, not just what happened.
3. SINGAPORE IMPLICATIONS is the most important section. Think like a Singaporean strategic planner:
   - How does this affect SAF readiness and force posture?
   - What are the economic exposure risks for Singapore?
   - How does this affect Singapore's diplomatic balancing act?
   - What should MFA/MINDEF/MTI be watching?
4. Rate overall urgency:
   - 🔴 CRITICAL: Immediate threat or opportunity requiring attention within 24-48h
   - 🟡 ELEVATED: Significant development requiring monitoring this week
   - 🟢 ROUTINE: Important context but no immediate action required
5. For "article_refs", list the ARTICLE NUMBERS (e.g. 1, 3, 5) from the sensor feed that support each development. This is critical for source attribution.

SENSOR INTELLIGENCE FEED:
{sensor_input}

Respond in this exact JSON format:
{{
  "overall_urgency": "ELEVATED",
  "headline": "One-line headline capturing the most significant development",
  "executive_summary": "2-3 sentence executive summary of the strategic picture",
  "key_developments": [
    {{
      "headline": "Short punchy headline (e.g. 'US space missile defense')",
      "analysis": "2-3 sentence analysis including second-order implications",
      "urgency": "ELEVATED",
      "article_refs": [1, 3],
      "category": "DEFENCE",
      "why": "ultra-short why (e.g. 'high-tech warfare shift')",
      "sg_impact": "ultra-short SG impact (e.g. 'upgrade C4ISR')"
    }}
  ],
  "singapore_implications": [
    "Specific implication for Singapore with reasoning"
  ],
  "watchlist": [
    "Item to monitor going forward"
  ]
}}

For each key_development:
- "category": Exactly one of: "DEFENCE", "GEOPOLITICS", or "GEOECONOMICS"
- "headline": Short punchy label (≤8 words, no verbs — noun phrases like 'US space missile defense')
- "why": Ultra-short consequence (≤6 words, use → ↑ ↓ arrows, e.g. 'partnership shift', 'regional spillover risk')
- "sg_impact": Ultra-short Singapore angle (≤5 words, e.g. 'upgrade C4ISR', 'maritime relevance ↓')

Aim for 3-6 key developments, 3-4 Singapore implications, and 3-4 watchlist items.
Be concise but insightful. Write like a senior intelligence analyst, not a journalist.
"""

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
                max_tokens=4000,
            )

            result = json.loads(response.choices[0].message.content)

            # Build developments with resolved source URLs
            developments = []
            for dev in result.get("key_developments", []):
                refs = dev.get("article_refs", [])
                resolved_sources = []
                resolved_urls = []
                for ref in refs:
                    if isinstance(ref, int) and ref in article_index:
                        resolved_sources.append(article_index[ref]["source"])
                        resolved_urls.append(article_index[ref]["url"])
                # Fallback: if LLM returned old-style "sources" strings
                if not resolved_urls and "sources" in dev:
                    resolved_sources = dev["sources"]
                developments.append(Development(
                    headline=dev.get("headline", ""),
                    analysis=dev.get("analysis", ""),
                    urgency=dev.get("urgency", "ROUTINE"),
                    sources=resolved_sources,
                    source_urls=resolved_urls,
                    category=dev.get("category", ""),
                    why=dev.get("why", ""),
                    sg_impact=dev.get("sg_impact", ""),
                ))

            brief = AnalystBrief(
                analyst_name=self.name,
                analyst_role=self.role,
                timestamp=datetime.now(timezone.utc).isoformat(),
                overall_urgency=result.get("overall_urgency", "ROUTINE"),
                headline=result.get("headline", "No significant developments"),
                executive_summary=result.get("executive_summary", ""),
                key_developments=developments,
                singapore_implications=result.get("singapore_implications", []),
                watchlist=result.get("watchlist", []),
            )

            # Generate formatted text for Telegram
            brief.raw_text = self._format_brief(brief)

            self.log.info(
                "━━━ ANALYST %s COMPLETE: %s — %d developments ━━━",
                self.name.upper(), brief.overall_urgency, len(brief.key_developments),
            )
            return brief

        except Exception as e:
            self.log.error("Analysis failed: %s", str(e))
            return self._placeholder_brief(reports)

    def _format_brief(self, brief: AnalystBrief) -> str:
        """Format the brief into rich text for Telegram delivery."""
        urgency_icons = {
            "CRITICAL": "🔴",
            "ELEVATED": "🟡",
            "ROUTINE": "🟢",
        }
        role_icons = {
            "Defence Strategist": "🎖️",
            "Geoeconomic Analyst": "📈",
        }

        icon = role_icons.get(self.role, "📋")
        urgency_icon = urgency_icons.get(brief.overall_urgency, "⚪")
        now = datetime.now(timezone.utc).strftime("%d %b %Y • %H%M UTC")

        lines = [
            f"━━━━━━━━━━━━━━━━━━━━━━━",
            f"{icon} <b>{self.role.upper()} BRIEF</b>",
            f"📅 {now}",
            f"{urgency_icon} <b>{brief.overall_urgency} THREAT LEVEL</b>",
            f"━━━━━━━━━━━━━━━━━━━━━━━",
            f"",
            f"📌 <b>HEADLINE</b>",
            f"{brief.headline}",
            f"",
            f"📝 <b>EXECUTIVE SUMMARY</b>",
            f"{brief.executive_summary}",
            f"",
            f"🔍 <b>KEY DEVELOPMENTS</b>",
        ]

        for i, dev in enumerate(brief.key_developments, 1):
            dev_icon = urgency_icons.get(dev.urgency, "⚪")
            lines.extend([
                f"",
                f"{dev_icon} <b>[{i}] {dev.headline}</b>",
                f"{dev.analysis}",
            ])
            # Show sources as bare URLs (Telegram auto-links them)
            if dev.source_urls:
                lines.append(f"→ {' · '.join(dev.source_urls)}")
            elif dev.sources:
                lines.append(f"→ {', '.join(dev.sources)}")

        lines.extend([
            f"",
            f"🇸🇬 <b>SINGAPORE IMPLICATIONS</b>",
        ])
        for impl in brief.singapore_implications:
            lines.append(f"• {impl}")

        lines.extend([
            f"",
            f"👁️ <b>WATCHLIST</b>",
        ])
        for item in brief.watchlist:
            lines.append(f"• {item}")

        lines.append(f"━━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)

    def _placeholder_brief(self, reports: list[SensorReport]) -> AnalystBrief:
        """Generate a placeholder brief when LLM is unavailable."""
        all_items = []
        for r in reports:
            all_items.extend(r.items)

        brief = AnalystBrief(
            analyst_name=self.name,
            analyst_role=self.role,
            timestamp=datetime.now(timezone.utc).isoformat(),
            overall_urgency="ROUTINE",
            headline="Sensor data collected — LLM analysis unavailable",
            executive_summary=f"Collected {len(all_items)} intelligence items across {len(reports)} sensors. Manual review recommended.",
            key_developments=[
                Development(
                    headline=item.headline,
                    analysis=item.summary,
                    urgency=item.relevance,
                    sources=[item.source],
                    source_urls=[item.url],
                )
                for item in all_items[:5]
            ],
            singapore_implications=["Manual analysis required — no LLM available"],
            watchlist=["Configure OPENAI_API_KEY for full analyst capability"],
        )
        brief.raw_text = self._format_brief(brief)
        return brief
