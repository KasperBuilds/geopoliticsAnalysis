# SENTINEL — Multi-Agent Geopolitical Intelligence System

An autonomous, agentic intelligence pipeline that continuously scans global defence and geopolitical sources, filters signal from noise, and delivers PhD-level strategic briefs focused on Singapore's implications via Telegram.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 1: SENSOR AGENTS                       │
│                                                                 │
│  🛡️ Defence   🌏 Geopolitics  📊 Trade   ⛏️ Materials          │
│  🇸🇬 Singapore  🏛️ Think Tanks                                 │
│                                                                 │
│  Each sensor: Scan RSS → Keyword Filter → LLM Extract → Report │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
┌───────────────────┤  ROUTING    ├───────────────────┐
│                   └─────────────┘                   │
│                                                     │
│  ┌──────────────────────────┐ ┌──────────────────────────┐
│  │ 🎖️ ANALYST ALPHA         │ │ 📈 ANALYST BRAVO          │
│  │ Defence Strategist       │ │ Geoeconomic Analyst      │
│  │                          │ │                          │
│  │ Receives:                │ │ Receives:                │
│  │ • Defence                │ │ • Trade                  │
│  │ • Geopolitics            │ │ • Materials              │
│  │ • Singapore              │ │ • Geopolitics            │
│  │ • Think Tanks            │ │ • Singapore              │
│  │                          │ │ • Think Tanks            │
│  └────────────┬─────────────┘ └────────────┬─────────────┘
│               │                            │
│               └──────────┬─────────────────┘
│                          │
│               ┌──────────▼──────────┐
│               │ 📱 TELEGRAM DELIVERY │
│               │ Rich formatted briefs│
│               └─────────────────────┘
└──────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone & Install

```bash
cd geopoliticsAnalysis
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and fill in:
- `OPENAI_API_KEY` — Get from [OpenAI](https://platform.openai.com/api-keys)
- `TELEGRAM_BOT_TOKEN` — Create a bot via [@BotFather](https://t.me/BotFather)
- `TELEGRAM_CHAT_ID` — Get your ID via [@userinfobot](https://t.me/userinfobot)

### 3. Run

```bash
# One-shot immediate briefing
python main.py --now

# Scheduled autonomous operation (0600, 1200, 1800 SGT)
python main.py
```

## Sensor Sources

| Sensor | Sources |
|--------|---------|
| 🛡️ Defence | Defense News, Defense.gov, Defense One, USNI, Breaking Defense, Janes |
| 🌏 Geopolitics | The Diplomat, Foreign Policy, Al Jazeera, BBC World, SCMP, CNA |
| 📊 Trade | SCMP Business, Nikkei Asia, CNA Business, BBC Business, FT |
| ⛏️ Materials | Mining.com, FreightWaves, Semiconductor Engineering, OilPrice |
| 🇸🇬 Singapore | CNA Singapore, Straits Times, MINDEF News, MFA Statements |
| 🏛️ Think Tanks | RSIS, IISS, CSIS, ASPI, ICG, War on the Rocks, Chatham House, Carnegie |

## Configuration

All settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | Required for LLM analyst reasoning |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model to use |
| `TELEGRAM_BOT_TOKEN` | — | Telegram bot token |
| `TELEGRAM_CHAT_ID` | — | Your Telegram chat ID |
| `SCHEDULE_HOURS` | `6,12,18` | Briefing hours (SGT) |
| `TIMEZONE` | `Asia/Singapore` | Schedule timezone |
| `LOG_LEVEL` | `INFO` | Logging verbosity |

## Cost Estimate

~8 GPT-4o API calls per pipeline run × 3 runs/day = ~24 calls/day.
At current GPT-4o pricing, expect **< $1/day** for typical article volumes.
