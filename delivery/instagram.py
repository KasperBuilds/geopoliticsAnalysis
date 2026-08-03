"""
SENTINEL — Instagram Stories Publisher
Centralised Meta Graph API client for Story container creation and publishing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from config import (
    INSTAGRAM_ACCOUNT_ID,
    INSTAGRAM_DRY_RUN,
    INSTAGRAM_PUBLISH_ENABLED,
    META_ACCESS_TOKEN,
    META_GRAPH_API_VERSION,
)
from utils.logger import get_logger

log = get_logger("instagram")


class InstagramAPIError(Exception):
    """Meta Graph API error with optional structured details."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: int | None = None,
        error_type: str | None = None,
        payload: dict | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_type = error_type
        self.payload = payload or {}

    @property
    def is_token_error(self) -> bool:
        return self.error_code in {190, 102} or (
            self.error_type == "OAuthException" and self.status_code in {400, 401}
        )

    @property
    def is_rate_limit(self) -> bool:
        return self.error_code in {4, 17, 32, 613, 80000, 80001} or self.status_code == 429


@dataclass
class StoryPublishResult:
    """Outcome of publishing one Story image."""

    index: int
    image_path: str
    image_url: str
    container_id: str | None = None
    media_id: str | None = None
    status: str = "pending"  # pending|published|dry_run|failed|skipped
    error: str | None = None


@dataclass
class InstagramPublishReport:
    """Aggregate publish report for a briefing run."""

    dry_run: bool
    publish_enabled: bool
    results: list[StoryPublishResult] = field(default_factory=list)
    stopped_early: bool = False
    error: str | None = None

    @property
    def published_count(self) -> int:
        return sum(1 for r in self.results if r.status == "published")

    @property
    def all_published(self) -> bool:
        return bool(self.results) and all(r.status == "published" for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "publish_enabled": self.publish_enabled,
            "stopped_early": self.stopped_early,
            "error": self.error,
            "published_count": self.published_count,
            "results": [
                {
                    "index": r.index,
                    "image_path": r.image_path,
                    "image_url": r.image_url,
                    "container_id": r.container_id,
                    "media_id": r.media_id,
                    "status": r.status,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


class InstagramClient:
    """
    Thin Meta Graph API client for Instagram Stories.

    Flow per image:
      1. POST /{ig-user-id}/media  media_type=STORIES
      2. Poll container status until FINISHED (when required)
      3. POST /{ig-user-id}/media_publish
    """

    def __init__(
        self,
        account_id: str | None = None,
        access_token: str | None = None,
        api_version: str | None = None,
        session: requests.Session | None = None,
    ):
        self.account_id = account_id if account_id is not None else INSTAGRAM_ACCOUNT_ID
        self.access_token = access_token if access_token is not None else META_ACCESS_TOKEN
        self.api_version = (api_version or META_GRAPH_API_VERSION or "v21.0").strip()
        if not self.api_version.startswith("v"):
            self.api_version = f"v{self.api_version}"
        self.session = session or requests.Session()
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    @property
    def configured(self) -> bool:
        return bool(self.account_id and self.access_token)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        timeout: int = 60,
    ) -> dict:
        params = dict(params or {})
        data = dict(data or {})
        # Never log the token — attach it only to the request
        if method.upper() == "GET":
            params["access_token"] = self.access_token
        else:
            data["access_token"] = self.access_token

        try:
            response = self.session.request(
                method=method.upper(),
                url=self._url(path),
                params=params if method.upper() == "GET" else None,
                data=data if method.upper() != "GET" else None,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise InstagramAPIError(f"Meta API network error: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text[:500]}

        if response.status_code >= 400 or "error" in payload:
            err = payload.get("error", {}) if isinstance(payload, dict) else {}
            message = err.get("message") or f"HTTP {response.status_code}"
            # Ensure token material never appears in raised messages
            safe_message = message.replace(self.access_token, "[redacted]") if self.access_token else message
            raise InstagramAPIError(
                safe_message,
                status_code=response.status_code,
                error_code=err.get("code"),
                error_type=err.get("type"),
                payload={"error": {k: v for k, v in err.items() if k != "message"} | {"message": safe_message}},
            )
        return payload

    def create_story_container(self, image_url: str) -> str:
        """Create an Instagram Story media container. Returns container ID."""
        payload = self._request(
            "POST",
            f"{self.account_id}/media",
            data={
                "image_url": image_url,
                "media_type": "STORIES",
            },
        )
        container_id = payload.get("id")
        if not container_id:
            raise InstagramAPIError("Media container response missing id", payload=payload)
        log.info("Created Story container %s", container_id)
        return str(container_id)

    def get_container_status(self, container_id: str) -> str:
        """Return container status_code (e.g. FINISHED, IN_PROGRESS, ERROR)."""
        payload = self._request(
            "GET",
            container_id,
            params={"fields": "status_code,status"},
        )
        return str(payload.get("status_code") or payload.get("status") or "UNKNOWN")

    def wait_for_container(
        self,
        container_id: str,
        *,
        timeout_seconds: float = 90.0,
        poll_interval: float = 2.0,
    ) -> str:
        """Poll until FINISHED or raise on ERROR / timeout."""
        deadline = time.time() + timeout_seconds
        last_status = "UNKNOWN"
        while time.time() < deadline:
            last_status = self.get_container_status(container_id)
            if last_status == "FINISHED":
                return last_status
            if last_status in {"ERROR", "EXPIRED"}:
                raise InstagramAPIError(
                    f"Container {container_id} entered terminal status {last_status}"
                )
            time.sleep(poll_interval)
        raise InstagramAPIError(
            f"Timed out waiting for container {container_id} (last status={last_status})"
        )

    def publish_container(self, container_id: str) -> str:
        """Publish a ready container. Returns published media ID."""
        payload = self._request(
            "POST",
            f"{self.account_id}/media_publish",
            data={"creation_id": container_id},
        )
        media_id = payload.get("id")
        if not media_id:
            raise InstagramAPIError("Publish response missing media id", payload=payload)
        log.info("Published Story media %s (container %s)", media_id, container_id)
        return str(media_id)

    def publish_story_image(self, image_url: str) -> tuple[str, str]:
        """Full create → wait → publish cycle for one Story image."""
        container_id = self.create_story_container(image_url)
        try:
            self.wait_for_container(container_id)
        except InstagramAPIError as exc:
            # Image containers sometimes become publishable immediately;
            # attempt publish once if status polling is inconclusive.
            if "Timed out" not in str(exc):
                raise
            log.warning("Container wait timed out — attempting publish anyway")
        media_id = self.publish_container(container_id)
        return container_id, media_id

    def build_create_container_request(self, image_url: str) -> dict[str, Any]:
        """Return the request shape for tests (token excluded)."""
        return {
            "method": "POST",
            "url": self._url(f"{self.account_id}/media"),
            "data": {
                "image_url": image_url,
                "media_type": "STORIES",
            },
        }

    def build_publish_request(self, container_id: str) -> dict[str, Any]:
        """Return the publish request shape for tests (token excluded)."""
        return {
            "method": "POST",
            "url": self._url(f"{self.account_id}/media_publish"),
            "data": {"creation_id": container_id},
        }


class InstagramStoryPublisher:
    """
    Orchestrates sequential Story publishing with dry-run and failure rules.

    Rules:
      - Publishing disabled by default
      - Dry-run never calls Meta
      - Stop the sequence if Story 1 fails
      - Later failures record which Stories already published (no auto-repost)
    """

    def __init__(self, client: InstagramClient | None = None):
        self.client = client or InstagramClient()
        self.dry_run = _as_bool(INSTAGRAM_DRY_RUN, default=True)
        self.publish_enabled = _as_bool(INSTAGRAM_PUBLISH_ENABLED, default=False)

    def should_publish(self) -> bool:
        return self.publish_enabled and not self.dry_run

    def publish_stories(
        self,
        image_paths: list[Path],
        image_urls: list[str] | None = None,
    ) -> InstagramPublishReport:
        """
        Publish Stories in order. image_urls required when actually publishing.
        """
        report = InstagramPublishReport(
            dry_run=self.dry_run,
            publish_enabled=self.publish_enabled,
        )

        if not image_paths:
            report.error = "No story images provided"
            return report

        urls = image_urls or [""] * len(image_paths)

        if not self.should_publish():
            mode = "DRY RUN" if self.dry_run or not self.publish_enabled else "SKIPPED"
            log.info(
                "Instagram publishing %s (enabled=%s dry_run=%s) — logging paths only",
                mode,
                self.publish_enabled,
                self.dry_run,
            )
            for i, path in enumerate(image_paths):
                report.results.append(
                    StoryPublishResult(
                        index=i + 1,
                        image_path=str(path),
                        image_url=urls[i] if i < len(urls) else "",
                        status="dry_run",
                    )
                )
                log.info("Story %d path: %s", i + 1, path)
            return report

        if not self.client.configured:
            report.error = "Instagram credentials not configured"
            log.error(report.error)
            return report

        for i, path in enumerate(image_paths):
            url = urls[i] if i < len(urls) else ""
            result = StoryPublishResult(
                index=i + 1,
                image_path=str(path),
                image_url=url,
            )
            try:
                if not url or url.startswith("file://"):
                    raise InstagramAPIError(
                        "Public HTTPS image URL required for Instagram publishing"
                    )
                container_id, media_id = self.client.publish_story_image(url)
                result.container_id = container_id
                result.media_id = media_id
                result.status = "published"
                report.results.append(result)
            except InstagramAPIError as exc:
                result.status = "failed"
                result.error = _safe_error_message(exc)
                report.results.append(result)
                report.error = result.error
                report.stopped_early = True
                log.error(
                    "Story %d publish failed — stopping sequence. Already published: %s. Error: %s",
                    i + 1,
                    [r.index for r in report.results if r.status == "published"],
                    result.error,
                )
                # Mark remaining as skipped (do not retry/repost published ones)
                for j in range(i + 1, len(image_paths)):
                    report.results.append(
                        StoryPublishResult(
                            index=j + 1,
                            image_path=str(image_paths[j]),
                            image_url=urls[j] if j < len(urls) else "",
                            status="skipped",
                            error="Skipped after earlier Story failure",
                        )
                    )
                break

        return report


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _safe_error_message(exc: Exception) -> str:
    text = str(exc)
    token = META_ACCESS_TOKEN
    if token and token in text:
        text = text.replace(token, "[redacted]")
    return text
