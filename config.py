"""
SENTINEL — Central Configuration
Loads environment variables and defines all source registries, keywords, and system constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env ───────────────────────────────────────────────
load_dotenv(Path(__file__).parent / ".env")

# ── Credentials ─────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Schedule ────────────────────────────────────────────────
TIMEZONE = os.getenv("TIMEZONE", "Asia/Singapore")
SCHEDULE_HOURS = [int(h) for h in os.getenv("SCHEDULE_HOURS", "6,12,18").split(",")]
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ── Database ────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "sentinel.db"

# ── Scraper Settings ────────────────────────────────────────
REQUEST_TIMEOUT = 15  # seconds
REQUEST_DELAY = 1.0   # seconds between requests (politeness)
MAX_ARTICLES_PER_FEED = 10
ARTICLE_MAX_AGE_HOURS = 96  # 4-day window — prevents premature re-ingestion of evolving stories
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
]

# ── Source Registries ───────────────────────────────────────
# Each sensor maps to a list of RSS feed URLs.

DEFENCE_SOURCES = [
    "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?max=10&ContentType=1&Site=945",
    "https://news.usni.org/feed",
    # Google News proxies for sources without working RSS
    "https://news.google.com/rss/search?q=site:defenseone.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:breakingdefense.com+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:janes.com+defence+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:reuters.com+military+defense+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:militarytimes.com+when:2d&hl=en-US&gl=US&ceid=US:en",
]

GEOPOLITICS_SOURCES = [
    "https://thediplomat.com/feed/",
    "https://foreignpolicy.com/feed/",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.scmp.com/rss/4/feed",
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6311",
    "https://news.google.com/rss/search?q=geopolitics+Indo-Pacific+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:reuters.com+geopolitics+diplomacy+when:2d&hl=en-US&gl=US&ceid=US:en",
]

TRADE_ECONOMICS_SOURCES = [
    "https://www.scmp.com/rss/5/feed",
    "https://asia.nikkei.com/rss/feed/nar",
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=6936",
    "https://feeds.bbci.co.uk/news/business/rss.xml",
    "https://news.google.com/rss/search?q=trade+tariff+sanctions+Asia+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:ft.com+trade+Asia+when:2d&hl=en-US&gl=US&ceid=US:en",
]

MATERIALS_SUPPLY_CHAIN_SOURCES = [
    "https://www.mining.com/feed/",
    "https://semiengineering.com/feed/",
    "https://www.hellenicshippingnews.com/feed/",
    "https://oilprice.com/rss/main",
    "https://news.google.com/rss/search?q=rare+earth+semiconductor+supply+chain+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=shipping+freight+disruption+when:2d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=critical+minerals+lithium+cobalt+when:2d&hl=en-US&gl=US&ceid=US:en",
]

SINGAPORE_SOURCES = [
    "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml&category=10416",
    "https://www.straitstimes.com/news/singapore/rss.xml",
    "https://news.google.com/rss/search?q=Singapore+defence+military+MINDEF+when:2d&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=Singapore+foreign+policy+MFA+when:2d&hl=en-SG&gl=SG&ceid=SG:en",
    "https://news.google.com/rss/search?q=Singapore+SAF+armed+forces+when:2d&hl=en-SG&gl=SG&ceid=SG:en",
]

THINKTANK_SOURCES = [
    "https://news.google.com/rss/search?q=site:rsis.edu.sg+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://www.aspistrategist.org.au/feed/",
    "https://warontherocks.com/feed/",
    "https://news.google.com/rss/search?q=site:csis.org+Indo-Pacific+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:iiss.org+Asia+defence+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:chathamhouse.org+Asia+security+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:crisisgroup.org+Asia+when:7d&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=site:carnegieendowment.org+Asia+when:7d&hl=en-US&gl=US&ceid=US:en",
]

# ── Keyword Registries ──────────────────────────────────────
# Used for fast local pre-filtering before LLM calls.

DEFENCE_KEYWORDS = [
    "military", "defence", "defense", "armed forces", "navy", "air force", "army",
    "missile", "submarine", "fighter jet", "aircraft carrier", "SAF", "MINDEF",
    "weapons", "arms deal", "deployment", "exercise", "wargame", "nuclear",
    "AUKUS", "NATO", "alliance", "deterrence", "force posture", "hypersonic",
    "cyber warfare", "drone", "UAV", "coast guard", "territorial",
]

GEOPOLITICS_KEYWORDS = [
    "geopolitics", "diplomacy", "sanctions", "sovereignty", "territorial dispute",
    "South China Sea", "Taiwan", "Indo-Pacific", "ASEAN", "QUAD", "Belt and Road",
    "bilateral", "multilateral", "summit", "treaty", "ceasefire", "conflict",
    "annexation", "blockade", "freedom of navigation", "FONOP", "proxy war",
    "regime", "coup", "election", "referendum", "UN Security Council",
]

TRADE_KEYWORDS = [
    "trade war", "tariff", "sanctions", "export controls", "FDI", "supply chain",
    "decoupling", "reshoring", "nearshoring", "free trade agreement", "RCEP",
    "CPTPP", "trade deficit", "currency", "central bank", "inflation",
    "semiconductor", "chips act", "economic coercion", "debt trap",
]

MATERIALS_KEYWORDS = [
    "rare earth", "lithium", "cobalt", "semiconductor", "chip shortage",
    "shipping disruption", "Strait of Malacca", "Suez Canal", "oil price",
    "LNG", "energy security", "critical minerals", "supply chain",
    "freight rates", "port congestion", "stockpile", "embargo",
]

SINGAPORE_KEYWORDS = [
    "Singapore", "SAF", "MINDEF", "MFA", "Changi", "Tuas", "Strait of Malacca",
    "RSAF", "RSN", "Total Defence", "National Service", "ASEAN chair",
    "smart nation", "Sentosa", "bilateral", "Singapore Armed Forces",
    "Lee Hsien Loong", "Lawrence Wong", "Vivian Balakrishnan",
]

THINKTANK_KEYWORDS = [
    # These feeds are already topic-filtered by Google News queries,
    # so keywords here are broad to avoid over-filtering.
    "China", "Taiwan", "Japan", "Korea", "India", "Philippines", "Vietnam",
    "Indonesia", "Myanmar", "Thailand", "Australia", "Pacific", "Asia",
    "Indo-Pacific", "ASEAN", "security", "defence", "defense", "military",
    "nuclear", "missile", "sanctions", "trade", "war", "conflict", "crisis",
    "alliance", "strategy", "geopolitics", "diplomacy", "threat", "risk",
    "maritime", "South China Sea", "semiconductor", "supply chain",
    "policy", "arms", "deterrence", "intelligence", "cyber",
]
