# SENTINEL — Multi-Agent Geopolitical Intelligence System

An autonomous intelligence pipeline that scans defence, geopolitics and geoeconomics sources, synthesises Singapore-focused briefs, delivers Telegram alerts, and publishes a daily four-frame Instagram Story briefing.

## Architecture

```
Sensors (RSS) → Analyst Alpha/Bravo (OpenRouter) → PDF + Telegram TL;DR
                                              ↘ Story composer (JSON)
                                                → Pillow Story renderer (4× 1080×1920)
                                                → Public object storage
                                                → Meta Instagram Stories API
```

- **Layer 1 — Sensors:** Defence, Geopolitics, Trade, Materials, Singapore, Think Tanks
- **Layer 2 — Analysts:** Defence Strategist + Geoeconomic Analyst
- **Layer 3 — Stories:** Validated Story JSON → four Story images → optional Instagram publish
- **Layer 4 — Telegram:** TL;DR, PDF, urgent status, optional Story preview / publish confirmation

Scheduling uses the existing APScheduler cron in Singapore time (default 06:00 / 12:00 / 18:00). GitHub Actions can also trigger `python main.py --now`.

## Quick Start

### 1. Install

```bash
cd geopoliticsAnalysis
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Minimum for Telegram briefs:

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Destination chat ID |

### 3. Dry-test Stories (no news / LLM / Instagram)

```bash
python main.py --stories-fixture
```

This renders four PNGs from `tests/fixtures/sample_story_brief.json` into `output/` and prints their paths.

### 4. Run the pipeline (dry-run Instagram by default)

```bash
# One-shot
python main.py --now

# Scheduled (0600, 1200, 1800 SGT)
python main.py
```

Instagram publishing is **disabled by default** (`INSTAGRAM_PUBLISH_ENABLED=false`, `INSTAGRAM_DRY_RUN=true`). The pipeline still collects news, summarises, renders Stories, archives JSON/images, and can preview via Telegram.

### 5. Publish to Instagram when ready

1. Complete Meta setup (see below).
2. Configure public object storage (`STORAGE_BACKEND=s3` + bucket credentials + `S3_PUBLIC_BASE_URL`).
3. Set in `.env`:

```bash
INSTAGRAM_PUBLISH_ENABLED=true
INSTAGRAM_DRY_RUN=false
INSTAGRAM_ACCOUNT_ID=your_ig_user_id
META_ACCESS_TOKEN=your_long_lived_token
STORAGE_BACKEND=s3
S3_BUCKET=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_PUBLIC_BASE_URL=https://your-public-cdn.example
```

4. Run:

```bash
python main.py --now
```

## Instagram Story output

Each successful cycle produces exactly four 1080×1920 images:

1. **Daily overview** — brand, Singapore date, risk level, headline, overview
2. **Top developments** — up to three items (fewer if warranted); each shows **What changed**, **Why it matters**, and a **Confirmed / Reported / Assessed** confidence tag
3. **Singapore posture / MINDEF** — 2–3 exposure areas, each with a **Read** (implication) and **SG Move** (concrete MINDEF/MFA response) + a Watch Next indicator
4. **Strategic Lens** — one established political-science / IR theory (e.g. Security Dilemma, Balance of Power, Thucydides Trap, Alliance Dilemma) with a grounded explanation of how the day's developments illustrate it, plus a one-line takeaway

Risk indicators: 🟢 Stable · 🟡 Elevated · 🟠 High · 🔴 Critical

Archives land in `output/YYYY-MM-DD/` (Singapore date) with:

- `briefing.json` — structured Story payload
- `sources.json` — grounding metadata
- `story_01_overview.png` / `story_02_developments.png` / `story_03_singapore.png` / `story_04_lens.png`
- `publication.json` — status, container/media IDs, errors

Successful runs are not overwritten; a later run creates `output/YYYY-MM-DD/run_HHMMSS/`.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | LLM via OpenRouter |
| `OPENROUTER_MODEL` | `openai/gpt-4o` | Model id |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | API base |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot |
| `TELEGRAM_CHAT_ID` | — | Telegram chat |
| `TELEGRAM_STORY_PREVIEW` | `true` | Preview/confirm Stories on Telegram |
| `INSTAGRAM_ACCOUNT_ID` | — | IG Business user id |
| `META_ACCESS_TOKEN` | — | Meta user token |
| `META_GRAPH_API_VERSION` | `v21.0` | Graph version |
| `INSTAGRAM_PUBLISH_ENABLED` | `false` | Master publish switch |
| `INSTAGRAM_DRY_RUN` | `true` | When true, never call Meta publish |
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `S3_BUCKET` / `S3_*` | — | Object storage for public image URLs |
| `SCHEDULE_HOURS` | `6,12,18` | SGT hours |
| `TIMEZONE` | `Asia/Singapore` | Schedule + archive dates |
| `OUTPUT_DIR` | `output` | Archive root |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Meta configuration (manual)

Complete these outside the repo before live publishing:

1. Convert the Instagram account to a **Business** (or professional) account linked to a Facebook Page.
2. Create a Meta Developer app with **Instagram** product / Graph API access.
3. Grant permissions: `instagram_basic`, `instagram_content_publish`, and Page-related permissions as required by Meta for your app type.
4. Obtain the **Instagram Business Account ID** (`INSTAGRAM_ACCOUNT_ID`).
5. Generate a **long-lived User access token** (`META_ACCESS_TOKEN`) and plan token rotation before expiry.
6. Host Story PNGs on **publicly reachable HTTPS** URLs (S3/R2 bucket with public read or CDN). Instagram cannot fetch `file://` or private objects.
7. Confirm the app is allowed to publish Stories for that IG user (Business account required; Creator-only accounts often fail).

## Tests

```bash
pip install -r requirements.txt
pytest -q
```

Coverage includes JSON validation, text-length limits, Story rendering/overflow, Singapore date conversion, dry-run behaviour, Meta request construction, publish order, and partial-failure handling. External APIs are mocked.

## Sensor Sources

| Sensor | Sources |
|--------|---------|
| Defence | Defense News, Defense.gov, Defense One, USNI, Breaking Defense, Janes |
| Geopolitics | The Diplomat, Foreign Policy, Al Jazeera, BBC World, SCMP, CNA |
| Trade | SCMP Business, Nikkei Asia, CNA Business, BBC Business, FT |
| Materials | Mining.com, Semiconductor Engineering, OilPrice, shipping feeds |
| Singapore | CNA Singapore, Straits Times, MINDEF/MFA queries |
| Think Tanks | RSIS, IISS, CSIS, ASPI, ICG, War on the Rocks, Chatham House, Carnegie |

## Cost Estimate

~8–10 OpenRouter calls per pipeline run (sensors + analysts + Story composer) × scheduled runs/day.
At typical GPT-4o-class pricing, expect on the order of **about $1/day** depending on volume and model choice.
