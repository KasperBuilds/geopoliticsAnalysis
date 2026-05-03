"""
SENTINEL — Deduplication Engine
Three-layer dedup:
  Layer 1: Exact URL hash  — catches literal reposts
  Layer 2: Title similarity — catches same-story-different-URL
  Layer 3: Narrative threads — tracks evolving storylines for analyst context
"""

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from config import DB_PATH, ARTICLE_MAX_AGE_HOURS
from utils.logger import get_logger

log = get_logger("dedup")

# ── Tuning Constants ────────────────────────────────────────
TITLE_SIMILARITY_THRESHOLD = 0.65   # titles ≥65% similar are considered dupes
TITLE_SIMILARITY_WINDOW_H = 96     # look back 96h for similar titles
NARRATIVE_MERGE_THRESHOLD = 0.55    # lower bar for grouping into same narrative
NARRATIVE_MAX_AGE_DAYS = 7          # keep narrative threads for 7 days


class DedupStore:
    """SQLite-backed article deduplication with narrative tracking."""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create all required tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_articles (
                    url_hash    TEXT PRIMARY KEY,
                    url         TEXT NOT NULL,
                    title       TEXT,
                    sensor      TEXT,
                    first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS briefs_archive (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    analyst     TEXT NOT NULL,
                    urgency     TEXT,
                    headline    TEXT,
                    content     TEXT,
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Layer 3: Narrative thread tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS narrative_threads (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_key      TEXT UNIQUE NOT NULL,
                    representative_title TEXT NOT NULL,
                    last_headline   TEXT NOT NULL,
                    article_count   INTEGER DEFAULT 1,
                    sensors         TEXT DEFAULT '',
                    first_seen      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        log.info("Dedup store initialised at %s", self.db_path)

    # ════════════════════════════════════════════════════════
    # LAYER 1: Exact URL Dedup
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _hash_url(url: str) -> str:
        """Generate a SHA-256 hash of a URL for dedup lookup."""
        return hashlib.sha256(url.strip().encode()).hexdigest()

    def is_seen(self, url: str) -> bool:
        """Check if an article URL has already been processed."""
        url_hash = self._hash_url(url)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM seen_articles WHERE url_hash = ?", (url_hash,)
            ).fetchone()
        return row is not None

    def mark_seen(self, url: str, title: str = "", sensor: str = ""):
        """Mark an article URL as processed."""
        url_hash = self._hash_url(url)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO seen_articles (url_hash, url, title, sensor)
                   VALUES (?, ?, ?, ?)""",
                (url_hash, url.strip(), title, sensor),
            )
            conn.commit()

    def mark_batch_seen(self, articles: list[dict], sensor: str = ""):
        """Mark multiple articles as seen in a single transaction."""
        with sqlite3.connect(self.db_path) as conn:
            for article in articles:
                url_hash = self._hash_url(article["url"])
                conn.execute(
                    """INSERT OR IGNORE INTO seen_articles (url_hash, url, title, sensor)
                       VALUES (?, ?, ?, ?)""",
                    (url_hash, article["url"].strip(), article.get("title", ""), sensor),
                )
            conn.commit()
        log.debug("Marked %d articles as seen for sensor [%s]", len(articles), sensor)

    # ════════════════════════════════════════════════════════
    # LAYER 2: Title Similarity Dedup
    # ════════════════════════════════════════════════════════

    def is_similar_title(self, new_title: str, threshold: float = TITLE_SIMILARITY_THRESHOLD) -> bool:
        """
        Check if a title is too similar to any recently seen article title.
        Uses SequenceMatcher for fast fuzzy matching — no LLM cost.
        Returns True if a near-duplicate is found (should be skipped).
        """
        if not new_title or len(new_title) < 10:
            return False

        cutoff = (datetime.now(timezone.utc) - timedelta(hours=TITLE_SIMILARITY_WINDOW_H)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT title FROM seen_articles WHERE first_seen > ? AND title != ''",
                (cutoff,),
            ).fetchall()

        new_lower = new_title.lower().strip()
        for (existing_title,) in rows:
            if not existing_title:
                continue
            ratio = SequenceMatcher(None, new_lower, existing_title.lower().strip()).ratio()
            if ratio >= threshold:
                log.debug(
                    "Title similarity %.2f ≥ %.2f — skipping: '%s' ≈ '%s'",
                    ratio, threshold, new_title[:60], existing_title[:60],
                )
                return True

        return False

    # ════════════════════════════════════════════════════════
    # LAYER 3: Narrative Thread Tracking
    # ════════════════════════════════════════════════════════

    @staticmethod
    def _normalise_title(title: str) -> str:
        """Normalise a title for narrative matching."""
        import re
        # Lowercase, strip punctuation, collapse whitespace
        t = title.lower().strip()
        t = re.sub(r"[^\w\s]", "", t)
        t = re.sub(r"\s+", " ", t)
        return t

    def update_narrative_thread(self, title: str, sensor: str = ""):
        """
        Check if this article belongs to an existing narrative thread.
        If so, increment its count and update the last headline.
        If not, create a new thread.
        """
        if not title or len(title) < 10:
            return

        normalised = self._normalise_title(title)

        with sqlite3.connect(self.db_path) as conn:
            # Fetch active threads from the last NARRATIVE_MAX_AGE_DAYS
            cutoff = (datetime.now(timezone.utc) - timedelta(days=NARRATIVE_MAX_AGE_DAYS)).isoformat()
            rows = conn.execute(
                """SELECT id, representative_title, article_count, sensors
                   FROM narrative_threads WHERE last_updated > ?""",
                (cutoff,),
            ).fetchall()

            best_match_id = None
            best_ratio = 0.0

            for (thread_id, rep_title, count, sensors_str) in rows:
                rep_norm = self._normalise_title(rep_title)
                ratio = SequenceMatcher(None, normalised, rep_norm).ratio()
                if ratio >= NARRATIVE_MERGE_THRESHOLD and ratio > best_ratio:
                    best_match_id = thread_id
                    best_ratio = ratio

            now = datetime.now(timezone.utc).isoformat()

            if best_match_id is not None:
                # Update existing thread
                conn.execute(
                    """UPDATE narrative_threads
                       SET article_count = article_count + 1,
                           last_headline = ?,
                           sensors = sensors || ',' || ?,
                           last_updated = ?
                       WHERE id = ?""",
                    (title, sensor, now, best_match_id),
                )
                log.debug("Narrative thread #%d updated (similarity %.2f): %s", best_match_id, best_ratio, title[:60])
            else:
                # Create new thread
                thread_key = hashlib.sha256(normalised.encode()).hexdigest()[:16]
                conn.execute(
                    """INSERT OR IGNORE INTO narrative_threads
                       (thread_key, representative_title, last_headline, article_count, sensors, first_seen, last_updated)
                       VALUES (?, ?, ?, 1, ?, ?, ?)""",
                    (thread_key, title, title, sensor, now, now),
                )
                log.debug("New narrative thread created: %s", title[:60])

            conn.commit()

    def update_narratives_batch(self, articles: list[dict], sensor: str = ""):
        """Update narrative threads for a batch of articles."""
        for article in articles:
            self.update_narrative_thread(article.get("title", ""), sensor)

    def get_active_narratives(self, min_articles: int = 2, max_age_days: int = NARRATIVE_MAX_AGE_DAYS) -> list[dict]:
        """
        Return active narrative threads that have been seen multiple times.
        These are the 'buildup' stories that analysts should be aware of.
        Returns list of dicts with: representative_title, last_headline, article_count, first_seen, last_updated
        """
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT representative_title, last_headline, article_count,
                          first_seen, last_updated
                   FROM narrative_threads
                   WHERE last_updated > ? AND article_count >= ?
                   ORDER BY article_count DESC, last_updated DESC
                   LIMIT 15""",
                (cutoff, min_articles),
            ).fetchall()

        narratives = []
        for (rep_title, last_headline, count, first_seen, last_updated) in rows:
            narratives.append({
                "representative_title": rep_title,
                "last_headline": last_headline,
                "article_count": count,
                "first_seen": first_seen,
                "last_updated": last_updated,
            })

        return narratives

    def format_narrative_context(self) -> str:
        """
        Build a text block summarising active narrative threads for injection
        into analyst prompts. Returns empty string if no active threads exist.
        """
        narratives = self.get_active_narratives(min_articles=2)
        if not narratives:
            return ""

        lines = [
            "PREVIOUSLY REPORTED NARRATIVES (do NOT repeat these unless there is a "
            "MATERIAL ESCALATION, new actor involvement, or genuinely new information):",
            "",
        ]
        for n in narratives:
            # Calculate how long this story has been running
            try:
                first = datetime.fromisoformat(n["first_seen"])
                days_running = (datetime.now(timezone.utc) - first).days
                age_str = f"since {first.strftime('%d %b')}" if days_running > 0 else "today"
            except (ValueError, TypeError):
                age_str = "recent"

            lines.append(
                f"- [{n['article_count']} articles {age_str}] "
                f"\"{n['representative_title'][:80]}\" — "
                f"last covered: \"{n['last_headline'][:80]}\""
            )

        lines.append("")
        lines.append(
            "If a story above has a MATERIAL UPDATE (escalation, de-escalation, new actors, "
            "concrete policy shift), include it and explicitly state what is NEW. "
            "Otherwise, omit it from your brief entirely."
        )
        return "\n".join(lines)

    # ════════════════════════════════════════════════════════
    # CLEANUP
    # ════════════════════════════════════════════════════════

    def purge_old(self):
        """Remove stale records from all tables."""
        article_cutoff = (datetime.now(timezone.utc) - timedelta(hours=ARTICLE_MAX_AGE_HOURS)).isoformat()
        narrative_cutoff = (datetime.now(timezone.utc) - timedelta(days=NARRATIVE_MAX_AGE_DAYS)).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            result_articles = conn.execute(
                "DELETE FROM seen_articles WHERE first_seen < ?",
                (article_cutoff,),
            )
            result_narratives = conn.execute(
                "DELETE FROM narrative_threads WHERE last_updated < ?",
                (narrative_cutoff,),
            )
            conn.commit()

        log.info(
            "Purged %d stale articles, %d expired narrative threads",
            result_articles.rowcount, result_narratives.rowcount,
        )

    def archive_brief(self, analyst: str, urgency: str, headline: str, content: str):
        """Archive a completed analyst brief for historical review."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO briefs_archive (analyst, urgency, headline, content)
                   VALUES (?, ?, ?, ?)""",
                (analyst, urgency, headline, content),
            )
            conn.commit()
        log.info("Archived brief from [%s]: %s", analyst, headline[:60])
