#!/usr/bin/env python3
"""
SENTINEL — Multi-Agent Geopolitical Intelligence System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Orchestrator: Wires sensors → analysts → Telegram delivery.
Runs autonomously on a schedule, or on-demand with --now.

Architecture:
  Layer 1: 6 Sensor Agents (Defence, Geopolitics, Trade, Materials, Singapore, Think Tank)
  Layer 2: 2 Synthesis Analysts (Defence Strategist, Geoeconomic Analyst)
  Layer 3: Telegram Delivery

Usage:
  python main.py          # Start scheduled operation (default: 0600, 1200, 1800 SGT)
  python main.py --now    # Run one immediate briefing cycle
"""

import argparse
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import TIMEZONE, SCHEDULE_HOURS, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# ── Sensors ─────────────────────────────────────────────────
from sensors.defence_sensor import DefenceSensor
from sensors.geopolitics_sensor import GeopoliticsSensor
from sensors.trade_sensor import TradeSensor
from sensors.materials_sensor import MaterialsSensor
from sensors.singapore_sensor import SingaporeSensor
from sensors.thinktank_sensor import ThinktankSensor

# ── Analysts ────────────────────────────────────────────────
from analysts.defence_analyst import DefenceAnalyst
from analysts.geoeconomic_analyst import GeoeconomicAnalyst

# ── Delivery ────────────────────────────────────────────────
from delivery.telegram_bot import TelegramDelivery

# ── Utilities ───────────────────────────────────────────────
from utils.dedup import DedupStore
from utils.logger import get_logger

log = get_logger("orchestrator")


# ════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ════════════════════════════════════════════════════════════

def run_sensor(sensor):
    """Run a single sensor and return its report. Used for concurrent execution."""
    try:
        return sensor.run()
    except Exception as e:
        log.error("Sensor [%s] failed: %s", sensor.name, str(e))
        return None


def run_pipeline():
    """
    Execute the full SENTINEL pipeline:
    1. All 6 sensors scan concurrently
    2. Sensor reports routed to appropriate analysts
    3. Both analysts produce briefs
    4. Briefs delivered via Telegram
    """
    pipeline_start = time.time()
    log.info("═" * 60)
    log.info("🛰️  SENTINEL PIPELINE ACTIVATED")
    log.info("═" * 60)

    # ── Phase 1: Sensor Scan (Concurrent) ───────────────────
    log.info("━━━ PHASE 1: SENSOR SCAN ━━━")
    sensors = [
        DefenceSensor(),
        GeopoliticsSensor(),
        TradeSensor(),
        MaterialsSensor(),
        SingaporeSensor(),
        ThinktankSensor(),
    ]

    reports = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_sensor = {executor.submit(run_sensor, s): s for s in sensors}
        for future in as_completed(future_to_sensor):
            sensor = future_to_sensor[future]
            try:
                report = future.result()
                if report:
                    reports[sensor.name] = report
                    log.info(
                        "✓ [%s] %d items from %d scanned",
                        sensor.name, len(report.items), report.total_articles_scanned,
                    )
            except Exception as e:
                log.error("✗ [%s] failed: %s", sensor.name, str(e))

    total_items = sum(len(r.items) for r in reports.values())
    log.info("Sensor phase complete: %d sensors, %d total items", len(reports), total_items)

    if total_items == 0:
        log.warning("No intelligence items collected — skipping analysis")
        delivery = TelegramDelivery()
        delivery.send_status_sync("⚠️ No significant intelligence items detected in this scan cycle.")
        return

    # ── Phase 2: Analyst Synthesis ──────────────────────────
    log.info("━━━ PHASE 2: ANALYST SYNTHESIS ━━━")

    # Route sensor reports to analysts — NO OVERLAP to avoid duplicate coverage
    # Alpha (Defence Strategist): military, geopolitics, singapore defence
    alpha_inputs = [
        reports.get("defence"),
        reports.get("geopolitics"),
        reports.get("singapore"),
    ]
    alpha_inputs = [r for r in alpha_inputs if r is not None]

    # Bravo (Geoeconomic Analyst): trade, materials, think tanks
    bravo_inputs = [
        reports.get("trade"),
        reports.get("materials"),
        reports.get("thinktank"),
    ]
    bravo_inputs = [r for r in bravo_inputs if r is not None]

    # Run analysts concurrently
    analyst_alpha = DefenceAnalyst()
    analyst_bravo = GeoeconomicAnalyst()
    briefs = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_alpha = executor.submit(analyst_alpha.analyse, alpha_inputs)
        future_bravo = executor.submit(analyst_bravo.analyse, bravo_inputs)

        for future, name in [(future_alpha, "Alpha"), (future_bravo, "Bravo")]:
            try:
                brief = future.result()
                if brief:
                    briefs.append(brief)
                    log.info(
                        "✓ Analyst %s: [%s] %s — %d developments",
                        name, brief.overall_urgency, brief.headline[:50], len(brief.key_developments),
                    )
            except Exception as e:
                log.error("✗ Analyst %s failed: %s", name, str(e))

    # ── Phase 3: Delivery ───────────────────────────────────
    log.info("━━━ PHASE 3: TELEGRAM DELIVERY ━━━")
    delivery = TelegramDelivery()

    if briefs:
        delivery.send_briefs_sync(briefs)

        # Archive briefs
        dedup = DedupStore()
        for brief in briefs:
            dedup.archive_brief(
                analyst=brief.analyst_name,
                urgency=brief.overall_urgency,
                headline=brief.headline,
                content=brief.raw_text,
            )
    else:
        log.warning("No analyst briefs produced")
        delivery.send_status_sync("⚠️ Analysts produced no briefs in this cycle.")

    # ── Phase 4: Cleanup ────────────────────────────────────
    dedup = DedupStore()
    dedup.purge_old()

    elapsed = time.time() - pipeline_start
    log.info("═" * 60)
    log.info("🛰️  SENTINEL PIPELINE COMPLETE — %.1fs elapsed", elapsed)
    log.info("═" * 60)


def start_scheduler():
    """Start the APScheduler for autonomous operation."""
    log.info("═" * 60)
    log.info("🛰️  SENTINEL — Autonomous Geopolitical Intelligence System")
    log.info("═" * 60)
    log.info("Schedule: %s SGT daily", ", ".join(f"{h:02d}:00" for h in SCHEDULE_HOURS))
    log.info("Timezone: %s", TIMEZONE)
    log.info("OpenAI:   %s", "✓ Configured" if OPENAI_API_KEY else "✗ NOT SET")
    log.info("Telegram: %s", "✓ Configured" if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else "✗ NOT SET")
    log.info("═" * 60)

    scheduler = BlockingScheduler()

    for hour in SCHEDULE_HOURS:
        scheduler.add_job(
            run_pipeline,
            trigger=CronTrigger(hour=hour, minute=0, timezone=TIMEZONE),
            id=f"sentinel_{hour:02d}00",
            name=f"SENTINEL Brief @ {hour:02d}00 SGT",
            misfire_grace_time=3600,
        )

    # Graceful shutdown
    def shutdown(signum, frame):
        log.info("Received shutdown signal — stopping scheduler")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log.info("Scheduler started — SENTINEL is now autonomous")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("SENTINEL shutting down")


# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="SENTINEL — Multi-Agent Geopolitical Intelligence System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py          Start scheduled operation (0600, 1200, 1800 SGT)
  python main.py --now    Run one immediate briefing cycle
        """,
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run one immediate briefing cycle and exit",
    )

    args = parser.parse_args()

    if args.now:
        log.info("Running immediate one-shot pipeline")
        run_pipeline()
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
