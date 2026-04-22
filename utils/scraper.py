"""
SENTINEL — Web Scraping Utilities
RSS feed parsing, article text extraction, and raw HTML scraping.
"""

import logging
import random
import re
import time
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup

from config import (
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
    MAX_ARTICLES_PER_FEED,
    ARTICLE_MAX_AGE_HOURS,
    USER_AGENTS,
)
from utils.logger import get_logger

log = get_logger("scraper")

# Suppress noisy tldextract cache warnings from newspaper4k
logging.getLogger("tldextract").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message=".*publicsuffix.*")


def _get_headers() -> dict:
    """Return request headers with a randomised User-Agent."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/rss+xml,application/xml,text/xml,application/atom+xml,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }


def _resolve_google_news_url(google_url: str) -> str:
    """
    Resolve a Google News redirect URL to the actual article URL.
    Uses a HEAD request to follow the redirect chain.
    """
    try:
        resp = requests.head(
            google_url,
            headers=_get_headers(),
            timeout=8,
            allow_redirects=True,
        )
        final_url = resp.url
        # Only return if we actually resolved away from Google
        if "news.google.com" not in final_url and "google.com" not in final_url:
            return final_url
    except Exception:
        pass

    # Fallback: try GET with stream to capture redirect without downloading body
    try:
        resp = requests.get(
            google_url,
            headers=_get_headers(),
            timeout=8,
            allow_redirects=True,
            stream=True,
        )
        final_url = resp.url
        resp.close()
        if "news.google.com" not in final_url and "google.com" not in final_url:
            return final_url
    except Exception:
        pass

    return google_url


def _extract_source_domain(url: str) -> str:
    """Extract a clean source domain name from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip www. prefix
        domain = re.sub(r"^www\.", "", domain)
        return domain
    except Exception:
        return "unknown"


def _is_google_news_feed(feed_url: str) -> bool:
    """Check if a feed URL is a Google News RSS feed."""
    return "news.google.com/rss" in feed_url


def fetch_rss(feed_url: str) -> list[dict]:
    """
    Parse an RSS/Atom feed and return a list of article dicts.
    Each dict: {title, url, published, summary, source_name}

    Uses requests to fetch raw content first (better timeout/header control),
    then passes to feedparser. Tolerates bozo feeds as long as they have entries.
    For Google News feeds, resolves redirect URLs and extracts real source names.
    """
    articles = []
    is_gnews = _is_google_news_feed(feed_url)

    try:
        # Fetch with requests first for better control
        try:
            resp = requests.get(
                feed_url,
                headers=_get_headers(),
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            resp.raise_for_status()
            raw_content = resp.content
        except requests.RequestException as e:
            log.warning("HTTP fetch failed for %s: %s", feed_url, str(e)[:100])
            return []

        # Parse the raw content
        feed = feedparser.parse(raw_content)

        # feedparser's bozo flag fires on many valid-but-imperfect feeds.
        # Only bail if bozo AND zero entries — otherwise process what we got.
        if feed.bozo and not feed.entries:
            log.warning("Feed empty/unparseable for %s: %s", feed_url, str(feed.bozo_exception)[:100])
            return []

        if feed.bozo and feed.entries:
            log.debug("Feed %s has bozo errors but %d entries recovered", feed_url, len(feed.entries))

        cutoff = datetime.now(timezone.utc) - timedelta(hours=ARTICLE_MAX_AGE_HOURS)

        for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
            # Parse published date
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass
            if not published and hasattr(entry, "updated_parsed") and entry.updated_parsed:
                try:
                    published = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            # Skip articles older than cutoff (but keep if no date available)
            if published and published < cutoff:
                continue

            raw_url = entry.get("link", "")
            if not raw_url:
                continue

            # Extract real source name for Google News entries
            source_name = ""
            article_url = raw_url

            if is_gnews:
                # Google News RSS includes source publisher in entry.source.title
                source_obj = entry.get("source", {})
                if hasattr(source_obj, "title"):
                    source_name = source_obj.title
                elif isinstance(source_obj, dict):
                    source_name = source_obj.get("title", "")

                # Resolve the Google News redirect to actual article URL
                resolved = _resolve_google_news_url(raw_url)
                if resolved != raw_url:
                    article_url = resolved
                    if not source_name:
                        source_name = _extract_source_domain(resolved)

            if not source_name:
                source_name = _extract_source_domain(article_url)

            article = {
                "title": entry.get("title", "No title"),
                "url": article_url,
                "published": published.isoformat() if published else "",
                "summary": _clean_html(entry.get("summary", entry.get("description", ""))),
                "source_name": source_name,
            }

            articles.append(article)

        log.debug("Fetched %d articles from %s", len(articles), feed_url)

    except Exception as e:
        log.error("Failed to process feed %s: %s", feed_url, str(e))

    return articles


def extract_article_text(url: str, max_chars: int = 3000) -> Optional[str]:
    """
    Extract the main article text from a URL using newspaper4k.
    Falls back to BeautifulSoup if newspaper fails.
    Returns truncated text up to max_chars.
    """
    try:
        from newspaper import Article

        article = Article(url)
        article.download()
        article.parse()

        text = article.text.strip()
        if text:
            return text[:max_chars]
    except Exception as e:
        log.debug("newspaper4k failed for %s: %s — trying BS4 fallback", url, str(e))

    # Fallback: BeautifulSoup
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        # Take the meatiest paragraphs
        paragraphs = [p for p in text.split("\n") if len(p) > 80]
        return "\n".join(paragraphs)[:max_chars]

    except Exception as e:
        log.error("All extraction methods failed for %s: %s", url, str(e))
        return None


def scrape_page(url: str, selector: str = "article") -> Optional[str]:
    """
    Scrape a web page and extract text from a CSS selector.
    Useful for non-RSS sources.
    """
    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(url, headers=_get_headers(), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        elements = soup.select(selector)
        if not elements:
            elements = soup.find_all("p")

        text = "\n".join(el.get_text(strip=True) for el in elements)
        return text[:3000] if text else None

    except Exception as e:
        log.error("Page scrape failed for %s: %s", url, str(e))
        return None


def _clean_html(text: str) -> str:
    """Strip HTML tags from a string."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator=" ", strip=True)[:500]
