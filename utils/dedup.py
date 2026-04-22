"""
SENTINEL — Deduplication Engine
SQLite-backed tracking of seen articles to prevent reprocessing.
"""

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from config import DB_PATH, ARTICLE_MAX_AGE_HOURS
from utils.logger import get_logger

log = get_logger("dedup")


class DedupStore:
    """SQLite-backed article deduplication."""

    def __init__(self, db_path: str = str(DB_PATH)):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create the articles table if it doesn't exist."""
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
            conn.commit()
        log.info("Dedup store initialised at %s", self.db_path)

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

    def purge_old(self):
        """Remove articles older than the configured max age."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=ARTICLE_MAX_AGE_HOURS)
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "DELETE FROM seen_articles WHERE first_seen < ?",
                (cutoff.isoformat(),),
            )
            conn.commit()
        log.info("Purged %d stale article records", result.rowcount)

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
