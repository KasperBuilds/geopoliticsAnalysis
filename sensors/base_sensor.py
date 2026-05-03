"""
SENTINEL — Base Sensor Agent
Abstract base class that all domain-specific sensors inherit from.
Handles the scan → filter → extract → report pipeline.
"""

import asyncio
import re
import time
from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse

from openai import OpenAI
from pydantic import BaseModel

from config import OPENAI_API_KEY, OPENAI_MODEL, REQUEST_DELAY
from utils.dedup import DedupStore
from utils.logger import get_logger
from utils.scraper import fetch_rss, extract_article_text


def _extract_domain(url: str) -> str:
    """Extract a clean domain name from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return re.sub(r"^www\.", "", domain)
    except Exception:
        return "unknown"


# ── Pydantic Models ─────────────────────────────────────────

class IntelItem(BaseModel):
    """A single intelligence item extracted from an article."""
    headline: str
    summary: str
    source: str
    url: str
    relevance: str  # HIGH, MEDIUM, LOW
    key_entities: list[str] = []
    published: str = ""


class SensorReport(BaseModel):
    """The output of a sensor scan — a filtered, extracted set of intel items."""
    sensor_name: str
    domain: str
    scan_time: str
    items: list[IntelItem] = []
    total_articles_scanned: int = 0
    total_articles_passed_filter: int = 0


class BaseSensor(ABC):
    """
    Abstract base sensor agent.

    Pipeline:
    1. scan()  — fetch articles from RSS feeds
    2. filter() — keyword-based pre-filtering (fast, local)
    3. extract() — LLM-powered relevance scoring + key-fact extraction
    4. report() — assemble SensorReport
    """

    def __init__(self):
        self.name = self._sensor_name()
        self.domain = self._domain()
        self.sources = self._sources()
        self.keywords = self._keywords()
        self.log = get_logger(f"sensor.{self.name}")
        self.dedup = DedupStore()
        self.client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

    @abstractmethod
    def _sensor_name(self) -> str:
        """Return the sensor's identifier name."""
        ...

    @abstractmethod
    def _domain(self) -> str:
        """Return the sensor's domain description."""
        ...

    @abstractmethod
    def _sources(self) -> list[str]:
        """Return list of RSS feed URLs to scan."""
        ...

    @abstractmethod
    def _keywords(self) -> list[str]:
        """Return list of keywords for pre-filtering."""
        ...

    def scan(self) -> list[dict]:
        """Fetch articles from all assigned RSS feeds."""
        all_articles = []
        for feed_url in self.sources:
            try:
                articles = fetch_rss(feed_url)
                all_articles.extend(articles)
                time.sleep(REQUEST_DELAY * 0.5)  # Be polite
            except Exception as e:
                self.log.error("Feed scan failed for %s: %s", feed_url, e)

        self.log.info("Scanned %d articles from %d feeds", len(all_articles), len(self.sources))
        return all_articles

    def filter(self, articles: list[dict]) -> list[dict]:
        """
        Fast local pre-filter using keyword matching.
        Removes duplicates and irrelevant articles before expensive LLM calls.
        """
        filtered = []
        keywords_lower = [k.lower() for k in self.keywords]

        for article in articles:
            # Layer 1: Skip if exact URL already seen
            if self.dedup.is_seen(article["url"]):
                continue

            # Layer 2: Skip if title is too similar to a recent article
            if self.dedup.is_similar_title(article.get("title", "")):
                continue

            # Keyword match on title + summary
            text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
            score = sum(1 for kw in keywords_lower if kw in text)

            if score >= 1:  # At least one keyword match
                article["keyword_score"] = score
                filtered.append(article)

        # Sort by keyword relevance, take top items
        filtered.sort(key=lambda x: x.get("keyword_score", 0), reverse=True)
        filtered = filtered[:15]  # Cap at 15 to control LLM costs

        self.log.info(
            "Filtered %d → %d articles (keyword match ≥ 1)",
            len(articles), len(filtered),
        )
        return filtered

    def extract(self, articles: list[dict]) -> list[IntelItem]:
        """
        LLM-powered extraction: score relevance and extract key facts.
        Processes articles in a single batched prompt for efficiency.
        """
        if not articles:
            return []

        if not self.client:
            self.log.warning("No OpenAI API key — returning keyword-filtered articles without LLM extraction")
            return self._fallback_extract(articles)

        # Build batch prompt
        articles_text = ""
        for i, art in enumerate(articles, 1):
            # Try to get article body for better analysis
            body = ""
            try:
                body_text = extract_article_text(art["url"], max_chars=1500)
                if body_text:
                    body = f"\n   Body excerpt: {body_text[:800]}"
            except Exception:
                pass

            source_name = art.get('source_name', _extract_domain(art['url']))
            articles_text += (
                f"\n[{i}] Title: {art['title']}\n"
                f"   Source: {source_name}\n"
                f"   URL: {art['url']}\n"
                f"   Summary: {art.get('summary', 'N/A')}"
                f"{body}\n"
            )

        prompt = f"""You are a {self.domain} intelligence analyst scanning raw news articles.
Your task: Evaluate each article's relevance to defence, geopolitics, and Singapore's strategic interests.

For each article, determine:
1. RELEVANCE: HIGH (directly impacts defence/geopolitics/Singapore), MEDIUM (indirectly relevant), or LOW (tangentially related)
2. A concise 2-3 sentence intelligence summary focusing on what matters strategically
3. Key entities (countries, organisations, leaders, weapons systems, trade items)

ONLY return articles rated HIGH or MEDIUM. Discard LOW relevance articles entirely.

Articles to evaluate:
{articles_text}

Respond in this exact JSON format:
{{
  "items": [
    {{
      "index": 1,
      "headline": "...",
      "summary": "...",
      "relevance": "HIGH",
      "key_entities": ["China", "PLA Navy", "South China Sea"]
    }}
  ]
}}

If no articles are relevant, return {{"items": []}}
"""

        try:
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": f"You are SENTINEL's {self.domain} sensor agent. Be precise, strategic, and concise."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=3000,
            )

            import json
            result = json.loads(response.choices[0].message.content)

            intel_items = []
            for item in result.get("items", []):
                idx = item.get("index", 1) - 1
                if 0 <= idx < len(articles):
                    art = articles[idx]
                    intel_items.append(IntelItem(
                        headline=item.get("headline", art["title"]),
                        summary=item.get("summary", art.get("summary", "")),
                        source=art.get("source_name", _extract_domain(art["url"])),
                        url=art["url"],
                        relevance=item.get("relevance", "MEDIUM"),
                        key_entities=item.get("key_entities", []),
                        published=art.get("published", ""),
                    ))

            self.log.info("LLM extraction: %d HIGH/MEDIUM items from %d candidates", len(intel_items), len(articles))
            return intel_items

        except Exception as e:
            self.log.error("LLM extraction failed: %s — using fallback", str(e))
            return self._fallback_extract(articles)

    def _fallback_extract(self, articles: list[dict]) -> list[IntelItem]:
        """Fallback extraction without LLM — uses keyword scores only."""
        items = []
        for art in articles:
            score = art.get("keyword_score", 0)
            relevance = "HIGH" if score >= 3 else "MEDIUM"
            items.append(IntelItem(
                headline=art["title"],
                summary=art.get("summary", ""),
                source=art.get("source_name", _extract_domain(art["url"])),
                url=art["url"],
                relevance=relevance,
                published=art.get("published", ""),
            ))
        return items

    def run(self) -> SensorReport:
        """Execute the full sensor pipeline: scan → filter → extract → report."""
        from datetime import datetime, timezone

        self.log.info("━━━ %s SENSOR ACTIVATED ━━━", self.name.upper())

        # 1. Scan
        articles = self.scan()
        total_scanned = len(articles)

        # 2. Filter
        filtered = self.filter(articles)
        total_filtered = len(filtered)

        # 3. Extract
        intel_items = self.extract(filtered)

        # 4. Mark as seen (Layer 1) + update narrative threads (Layer 3)
        self.dedup.mark_batch_seen(
            [{"url": art["url"], "title": art.get("title", "")} for art in filtered],
            sensor=self.name,
        )
        self.dedup.update_narratives_batch(
            [{"title": art.get("title", "")} for art in filtered],
            sensor=self.name,
        )

        # 5. Build report
        report = SensorReport(
            sensor_name=self.name,
            domain=self.domain,
            scan_time=datetime.now(timezone.utc).isoformat(),
            items=intel_items,
            total_articles_scanned=total_scanned,
            total_articles_passed_filter=total_filtered,
        )

        self.log.info(
            "━━━ %s COMPLETE: %d items from %d scanned ━━━",
            self.name.upper(), len(intel_items), total_scanned,
        )
        return report
