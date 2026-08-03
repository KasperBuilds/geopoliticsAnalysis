"""
SENTINEL — Public Object Storage
Uploads Story images to configured S3-compatible storage and verifies public URLs.
"""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

from config import (
    S3_ACCESS_KEY_ID,
    S3_BUCKET,
    S3_ENDPOINT_URL,
    S3_PUBLIC_BASE_URL,
    S3_REGION,
    S3_SECRET_ACCESS_KEY,
    STORAGE_BACKEND,
)
from utils.logger import get_logger

log = get_logger("storage")


class StorageError(Exception):
    """Raised when object storage upload or verification fails."""


class PublicObjectStorage:
    """
    Upload local files to publicly reachable object storage.

    Backends:
      - local: no upload; returns file:// URLs (not usable by Instagram)
      - s3: S3-compatible upload via boto3 (AWS S3, Cloudflare R2, MinIO)
    """

    def __init__(self):
        self.backend = (STORAGE_BACKEND or "local").lower().strip()

    def upload_file(self, local_path: Path, object_key: str) -> str:
        """Upload a file and return its public HTTPS URL."""
        local_path = Path(local_path)
        if not local_path.exists():
            raise StorageError(f"File not found: {local_path}")

        if self.backend == "local":
            url = local_path.resolve().as_uri()
            log.info("Storage [local]: %s -> %s", local_path.name, url)
            return url

        if self.backend == "s3":
            return self._upload_s3(local_path, object_key)

        raise StorageError(f"Unsupported STORAGE_BACKEND: {self.backend}")

    def _upload_s3(self, local_path: Path, object_key: str) -> str:
        if not S3_BUCKET:
            raise StorageError("S3_BUCKET is required for s3 storage backend")
        if not S3_ACCESS_KEY_ID or not S3_SECRET_ACCESS_KEY:
            raise StorageError("S3 credentials are required for s3 storage backend")

        try:
            import boto3
            from botocore.client import Config as BotoConfig
        except ImportError as exc:
            raise StorageError(
                "boto3 is required for S3 uploads — pip install boto3"
            ) from exc

        client_kwargs: dict = {
            "service_name": "s3",
            "aws_access_key_id": S3_ACCESS_KEY_ID,
            "aws_secret_access_key": S3_SECRET_ACCESS_KEY,
            "region_name": S3_REGION or "auto",
            "config": BotoConfig(signature_version="s3v4"),
        }
        if S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = S3_ENDPOINT_URL

        content_type = mimetypes.guess_type(str(local_path))[0] or "image/png"
        client = boto3.client(**client_kwargs)

        extra_args = {"ContentType": content_type}
        # Some providers ignore ACL; public access is usually via bucket policy
        try:
            client.upload_file(
                str(local_path),
                S3_BUCKET,
                object_key,
                ExtraArgs={**extra_args, "ACL": "public-read"},
            )
        except Exception:
            # Retry without ACL for R2 / locked-down buckets
            client.upload_file(
                str(local_path),
                S3_BUCKET,
                object_key,
                ExtraArgs=extra_args,
            )

        public_url = self._public_url(object_key)
        log.info("Uploaded %s -> %s", local_path.name, self._redact_url(public_url))
        return public_url

    def _public_url(self, object_key: str) -> str:
        if S3_PUBLIC_BASE_URL:
            base = S3_PUBLIC_BASE_URL.rstrip("/") + "/"
            return urljoin(base, object_key.lstrip("/"))
        if S3_ENDPOINT_URL:
            return f"{S3_ENDPOINT_URL.rstrip('/')}/{S3_BUCKET}/{object_key.lstrip('/')}"
        region = S3_REGION or "us-east-1"
        return f"https://{S3_BUCKET}.s3.{region}.amazonaws.com/{object_key.lstrip('/')}"

    def verify_public_url(self, url: str, timeout: int = 15) -> bool:
        """Confirm the URL is publicly reachable over HTTP(S)."""
        if url.startswith("file://"):
            log.warning("URL is local (file://) — not publicly reachable")
            return False
        try:
            response = requests.head(url, timeout=timeout, allow_redirects=True)
            if response.status_code >= 400:
                # Some hosts block HEAD — fall back to ranged GET
                response = requests.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                    headers={"Range": "bytes=0-64"},
                )
            ok = response.status_code < 400
            if not ok:
                log.error(
                    "Public URL check failed (%s): %s",
                    response.status_code,
                    self._redact_url(url),
                )
            return ok
        except requests.RequestException as exc:
            log.error("Public URL check error for %s: %s", self._redact_url(url), str(exc))
            return False

    def upload_and_verify(
        self,
        local_path: Path,
        object_key: str,
        retries: int = 3,
        retry_delay: float = 1.5,
    ) -> str:
        """Upload then verify public reachability with short retries."""
        url = self.upload_file(local_path, object_key)
        for attempt in range(retries):
            if self.verify_public_url(url):
                return url
            time.sleep(retry_delay * (attempt + 1))
        raise StorageError(f"Uploaded object not publicly reachable: {self._redact_url(url)}")

    @staticmethod
    def _redact_url(url: str) -> str:
        """Avoid logging query tokens if present."""
        if "?" in url:
            return url.split("?", 1)[0] + "?[redacted]"
        return url
