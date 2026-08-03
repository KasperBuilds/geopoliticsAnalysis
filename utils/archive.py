"""
SENTINEL — Run Archive
Persists Story briefing JSON, images, sources and publication status under output/.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from analysts.story_brief import StoryBriefing, singapore_date_folder
from config import OUTPUT_DIR, TIMEZONE
from delivery.instagram import InstagramPublishReport
from utils.logger import get_logger

log = get_logger("archive")


class ArchiveError(Exception):
    """Raised when archival cannot proceed safely."""


class RunArchive:
    """Manage per-day run folders: output/YYYY-MM-DD[/run_HHMMSS]."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = Path(base_dir or OUTPUT_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def resolve_run_dir(
        self,
        *,
        force: bool = False,
        when: datetime | None = None,
    ) -> Path:
        """
        Choose an archive directory for this run.

        - Prefer output/YYYY-MM-DD when empty or force=True
        - If a successful prior run exists and force is False, create a timestamped subfolder
          so successful runs are not overwritten.
        """
        date_key = singapore_date_folder(when)
        day_dir = self.base_dir / date_key

        if force or not day_dir.exists():
            day_dir.mkdir(parents=True, exist_ok=True)
            return day_dir

        status_path = day_dir / "publication.json"
        if status_path.exists():
            try:
                status = json.loads(status_path.read_text(encoding="utf-8"))
                if status.get("success"):
                    stamp = datetime.now(ZoneInfo(TIMEZONE)).strftime("%H%M%S")
                    run_dir = day_dir / f"run_{stamp}"
                    run_dir.mkdir(parents=True, exist_ok=True)
                    log.info(
                        "Prior successful archive exists — writing to %s",
                        run_dir,
                    )
                    return run_dir
            except (json.JSONDecodeError, OSError):
                pass

        day_dir.mkdir(parents=True, exist_ok=True)
        return day_dir

    def save_briefing(self, run_dir: Path, briefing: StoryBriefing) -> Path:
        path = run_dir / "briefing.json"
        path.write_text(
            json.dumps(briefing.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        sources_path = run_dir / "sources.json"
        sources_path.write_text(
            json.dumps(
                [s.model_dump() for s in briefing.sources],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        log.info("Archived briefing JSON -> %s", path)
        return path

    def save_images(self, run_dir: Path, image_paths: list[Path]) -> list[Path]:
        saved: list[Path] = []
        for src in image_paths:
            src = Path(src)
            dest = run_dir / src.name
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            saved.append(dest)
        return saved

    def save_publication(
        self,
        run_dir: Path,
        report: InstagramPublishReport | None,
        *,
        success: bool,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> Path:
        now = datetime.now(ZoneInfo(TIMEZONE))
        payload: dict[str, Any] = {
            "generated_at_sgt": now.isoformat(),
            "success": success,
            "error": error,
            "publication": report.to_dict() if report else None,
        }
        if extra:
            payload.update(extra)
        path = run_dir / "publication.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("Archived publication status -> %s", path)
        return path

    def write_manifest(
        self,
        run_dir: Path,
        *,
        briefing: StoryBriefing,
        image_paths: list[Path],
        report: InstagramPublishReport | None,
        success: bool,
        error: str | None = None,
    ) -> Path:
        """Convenience: persist briefing + publication metadata together."""
        self.save_briefing(run_dir, briefing)
        self.save_images(run_dir, image_paths)
        return self.save_publication(
            run_dir,
            report,
            success=success,
            error=error,
            extra={
                "brief_date": briefing.brief_date,
                "risk_level": briefing.risk_level,
                "image_files": [Path(p).name for p in image_paths],
                "source_count": len(briefing.sources),
            },
        )
