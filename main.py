#!/usr/bin/env python3
"""
SENTINEL — Multi-Agent Geopolitical Intelligence System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Orchestrator: Wires sensors → analysts → Story render → Instagram / Telegram.
Runs autonomously on a schedule, or on-demand with --now.

Architecture:
  Layer 1: 6 Sensor Agents (Defence, Geopolitics, Trade, Materials, Singapore, Think Tank)
  Layer 2: 2 Synthesis Analysts (Defence Strategist, Geoeconomic Analyst)
  Layer 3: Instagram Story composer + renderer + Meta publish
  Layer 4: Telegram (urgent alerts / TL;DR / optional Story preview)

Usage:
  python main.py                 # Start scheduled operation (default: 0600, 1200, 1800 SGT)
  python main.py --now           # Run one immediate briefing cycle
  python main.py --stories-fixture   # Render sample Stories from fixture data (no APIs)
"""

import argparse
import json
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    TIMEZONE,
    SCHEDULE_HOURS,
    OPENROUTER_API_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    INSTAGRAM_PUBLISH_ENABLED,
    INSTAGRAM_DRY_RUN,
    TELEGRAM_STORY_PREVIEW,
    OUTPUT_DIR,
)

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
from analysts.story_brief import (
    StoryBriefComposer,
    StoryBriefValidationError,
    validate_story_briefing,
)

# ── Delivery ────────────────────────────────────────────────
from delivery.telegram_bot import TelegramDelivery
from delivery.instagram import InstagramStoryPublisher, InstagramPublishReport

# ── Utilities ───────────────────────────────────────────────
from utils.dedup import DedupStore
from utils.pdf_report import PDFReportGenerator
from utils.story_renderer import StoryRenderer, StoryRenderError
from utils.storage import PublicObjectStorage, StorageError
from utils.archive import RunArchive
from utils.logger import get_logger

log = get_logger("orchestrator")

FIXTURE_PATH = Path(__file__).parent / "tests" / "fixtures" / "sample_story_brief.json"


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


def _as_bool(value, default=False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _notify_error(delivery: TelegramDelivery, message: str) -> None:
    try:
        delivery.send_status_sync(f"❌ {message}")
    except Exception as exc:
        log.error("Failed to send Telegram error notification: %s", str(exc))


def run_instagram_story_phase(
    briefs,
    delivery: TelegramDelivery,
    *,
    force_archive: bool = False,
) -> InstagramPublishReport | None:
    """
    Compose Story JSON → render 3 images → archive → optionally publish to Instagram.
    Returns the publish report, or None if the phase could not start.
    """
    log.info("━━━ PHASE 5: INSTAGRAM STORY BRIEF ━━━")
    archive = RunArchive()
    run_dir = archive.resolve_run_dir(force=force_archive)
    report: InstagramPublishReport | None = None

    try:
        composer = StoryBriefComposer()
        briefing = composer.compose(briefs)
    except StoryBriefValidationError as exc:
        msg = f"Story LLM validation failed — Instagram publish aborted. {exc}"
        log.error(msg)
        archive.save_publication(
            run_dir,
            None,
            success=False,
            error=str(exc),
        )
        _notify_error(delivery, msg)
        return None
    except Exception as exc:
        msg = f"Story composition failed — Instagram publish aborted. {exc}"
        log.error(msg)
        archive.save_publication(run_dir, None, success=False, error=str(exc))
        _notify_error(delivery, msg)
        return None

    try:
        renderer = StoryRenderer()
        image_paths = renderer.render_all(briefing, run_dir)
    except StoryRenderError as exc:
        msg = f"Story rendering failed — Instagram publish aborted. {exc}"
        log.error(msg)
        archive.save_briefing(run_dir, briefing)
        archive.save_publication(run_dir, None, success=False, error=str(exc))
        _notify_error(delivery, msg)
        return None

    # Persist structured briefing + sources even before publish attempt
    archive.save_briefing(run_dir, briefing)

    publisher = InstagramStoryPublisher()
    image_urls: list[str] = []

    if publisher.should_publish():
        storage = PublicObjectStorage()
        date_key = run_dir.name if run_dir.name.startswith("20") else run_dir.parent.name
        try:
            for path in image_paths:
                key = f"sentinel/stories/{date_key}/{path.name}"
                url = storage.upload_and_verify(path, key)
                image_urls.append(url)
        except StorageError as exc:
            msg = f"Story image upload failed — Instagram publish aborted. {exc}"
            log.error(msg)
            report = InstagramPublishReport(
                dry_run=publisher.dry_run,
                publish_enabled=publisher.publish_enabled,
                error=str(exc),
            )
            archive.save_publication(run_dir, report, success=False, error=str(exc))
            _notify_error(delivery, msg)
            return report
    else:
        log.info("Instagram dry-run / publish disabled — skipping public upload")
        for path in image_paths:
            log.info("Generated Story image: %s", path)

    report = publisher.publish_stories(image_paths, image_urls or None)
    success = (
        report.all_published
        if publisher.should_publish()
        else report.error is None and len(image_paths) == 3
    )
    archive.save_publication(
        run_dir,
        report,
        success=success,
        error=report.error,
        extra={
            "brief_date": briefing.brief_date,
            "risk_level": briefing.risk_level,
            "image_files": [p.name for p in image_paths],
            "source_count": len(briefing.sources),
            "telegram_summary": briefing.telegram_summary,
        },
    )

    # Optional Telegram confirmation / preview
    if _as_bool(TELEGRAM_STORY_PREVIEW, True):
        try:
            if publisher.should_publish() and report.all_published:
                delivery.send_status_sync(
                    f"✅ Instagram Stories published ({report.published_count}/3)\n"
                    f"{briefing.risk_level} — {briefing.headline}\n"
                    f"{briefing.telegram_summary}"
                )
            elif publisher.should_publish() and report.error:
                _notify_error(
                    delivery,
                    f"Instagram publish incomplete "
                    f"({report.published_count}/3 published). {report.error}",
                )
            else:
                # Dry-run preview: send first story image + summary
                if image_paths:
                    delivery.send_infographic_sync(
                        Path(image_paths[0]).read_bytes(),
                        caption=(
                            f"🛰️ <b>SENTINEL STORY PREVIEW</b> (dry-run)\n"
                            f"{briefing.risk_level} — {briefing.headline}\n"
                            f"{briefing.telegram_summary}"
                        ),
                    )
                for path in image_paths[1:]:
                    delivery.send_infographic_sync(Path(path).read_bytes())
        except Exception as exc:
            log.error("Telegram story preview/confirmation failed: %s", str(exc))

    return report


def run_pipeline():
    """
    Execute the full SENTINEL pipeline:
    1. All 6 sensors scan concurrently
    2. Sensor reports routed to appropriate analysts
    3. PDF report generated
    4. TL;DR + PDF delivered via Telegram
    5. Instagram Story compose → render → archive → publish (if enabled)
    """
    pipeline_start = time.time()
    log.info("═" * 60)
    log.info("🛰️  SENTINEL PIPELINE ACTIVATED")
    log.info("═" * 60)

    delivery = TelegramDelivery()

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
        log.warning("No intelligence items collected — skipping analysis and Instagram publish")
        delivery.send_status_sync(
            "⚠️ No significant intelligence items detected in this scan cycle. "
            "Instagram Stories were not published."
        )
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

    if not briefs:
        log.warning("No analyst briefs produced — skipping Instagram publish")
        delivery.send_status_sync(
            "⚠️ Analysts produced no briefs in this cycle. Instagram Stories were not published."
        )
        # Cleanup still runs below
    else:
        # ── Phase 3: PDF Report ─────────────────────────────────
        log.info("━━━ PHASE 3: PDF REPORT GENERATION ━━━")
        pdf_bytes = None
        try:
            pg = PDFReportGenerator()
            pdf_bytes = pg.generate(briefs)
            if pdf_bytes:
                log.info("✓ PDF report ready (%d KB)", len(pdf_bytes) // 1024)
            else:
                log.warning("PDF generation returned None — skipping document")
        except Exception as e:
            log.error("PDF generation failed: %s", str(e))

        # ── Phase 4: Delivery (TL;DR + PDF) ─────────────────────
        log.info("━━━ PHASE 4: TELEGRAM DELIVERY ━━━")
        delivery.send_tldr_sync(briefs)
        if pdf_bytes:
            delivery.send_pdf_sync(
                pdf_bytes,
                caption="📄 <b>SENTINEL PDF REPORT</b> — Full intelligence briefing",
            )

        # Archive briefs
        dedup = DedupStore()
        for brief in briefs:
            dedup.archive_brief(
                analyst=brief.analyst_name,
                urgency=brief.overall_urgency,
                headline=brief.headline,
                content=brief.raw_text,
            )

        # ── Phase 5: Instagram Stories ──────────────────────────
        run_instagram_story_phase(briefs, delivery)

    # ── Phase 6: Cleanup ────────────────────────────────────
    dedup = DedupStore()
    dedup.purge_old()

    elapsed = time.time() - pipeline_start
    log.info("═" * 60)
    log.info("🛰️  SENTINEL PIPELINE COMPLETE — %.1fs elapsed", elapsed)
    log.info("═" * 60)


def run_stories_fixture(output_dir: Path | None = None) -> list[Path]:
    """
    Generate sample Stories from fixture JSON — no news, LLM, or Instagram APIs.
    """
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Fixture not found: {FIXTURE_PATH}")

    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    briefing = validate_story_briefing(data)

    out = Path(output_dir or (OUTPUT_DIR / "fixture"))
    out.mkdir(parents=True, exist_ok=True)

    renderer = StoryRenderer()
    paths = renderer.render_all(briefing, out)

    archive = RunArchive()
    # Also write a dated archive copy for inspection
    run_dir = archive.resolve_run_dir(force=False)
    archive.write_manifest(
        run_dir,
        briefing=briefing,
        image_paths=paths,
        report=InstagramPublishReport(dry_run=True, publish_enabled=False),
        success=True,
        error=None,
    )

    print("Sample Stories generated (no external APIs called):")
    for path in paths:
        print(f"  {path}")
    print(f"Archived under: {run_dir}")
    return paths


def start_scheduler():
    """Start the APScheduler for autonomous operation."""
    log.info("═" * 60)
    log.info("🛰️  SENTINEL — Autonomous Geopolitical Intelligence System")
    log.info("═" * 60)
    log.info("Schedule: %s SGT daily", ", ".join(f"{h:02d}:00" for h in SCHEDULE_HOURS))
    log.info("Timezone: %s", TIMEZONE)
    log.info("OpenRouter: %s", "✓ Configured" if OPENROUTER_API_KEY else "✗ NOT SET")
    log.info("Telegram: %s", "✓ Configured" if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID else "✗ NOT SET")
    log.info(
        "Instagram: publish_enabled=%s dry_run=%s",
        INSTAGRAM_PUBLISH_ENABLED,
        INSTAGRAM_DRY_RUN,
    )
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
  python main.py                   Start scheduled operation (0600, 1200, 1800 SGT)
  python main.py --now             Run one immediate briefing cycle
  python main.py --stories-fixture Generate sample Stories from fixture data
        """,
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run one immediate briefing cycle and exit",
    )
    parser.add_argument(
        "--stories-fixture",
        action="store_true",
        help="Render sample Instagram Stories from fixture JSON (no news/LLM/Instagram APIs)",
    )
    parser.add_argument(
        "--fixture-output",
        type=str,
        default="",
        help="Optional output directory for --stories-fixture",
    )

    args = parser.parse_args()

    if args.stories_fixture:
        out = Path(args.fixture_output) if args.fixture_output else None
        run_stories_fixture(out)
        return

    if args.now:
        log.info("Running immediate one-shot pipeline")
        run_pipeline()
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
