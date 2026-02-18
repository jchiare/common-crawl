"""Fetch raw HTML from Common Crawl WARC files.

Supports two fetch backends:
  1. **S3 (preferred)**: Direct byte-range reads from the ``commoncrawl`` S3
     bucket using boto3.  This is the fastest and most reliable method; the
     bucket is publicly accessible (no credentials needed with unsigned
     requests).
  2. **HTTPS fallback**: Byte-range GET requests to data.commoncrawl.org via
     httpx.  Useful when boto3 is not installed or S3 access is blocked.

Given a CrawlRecord (with filename, offset, length), we fetch exactly
that byte range, decompress the WARC record, and extract the HTTP
response body (HTML).
"""

from __future__ import annotations

import gzip
import logging
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from typing import Iterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from warcio.archiveiterator import ArchiveIterator

from fde_job_atlas.models import CrawlRecord

logger = logging.getLogger(__name__)

WARC_S3_BUCKET = "commoncrawl"
WARC_HTTPS_PREFIX = "https://data.commoncrawl.org/"


class FetchBackend(str, Enum):
    S3 = "s3"
    HTTPS = "https"
    AUTO = "auto"


@dataclass
class FetchedPage:
    """A fetched HTML page with its source metadata."""

    record: CrawlRecord
    html: str
    http_status: int = 200
    http_headers: dict[str, str] | None = None


# ── S3 backend ──────────────────────────────────────────────────────


def _get_s3_client():  # type: ignore[no-untyped-def]
    """Create a boto3 S3 client configured for unsigned (public) access."""
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client("s3", config=Config(signature_version=UNSIGNED))


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
def _fetch_warc_range_s3(
    s3_client: object,
    filename: str,
    offset: int,
    length: int,
) -> bytes:
    """Fetch a byte range from a WARC file in the commoncrawl S3 bucket."""
    end = offset + length - 1
    resp = s3_client.get_object(  # type: ignore[union-attr]
        Bucket=WARC_S3_BUCKET,
        Key=filename,
        Range=f"bytes={offset}-{end}",
    )
    return resp["Body"].read()


# ── HTTPS backend ───────────────────────────────────────────────────


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
def _fetch_warc_range_https(
    client: httpx.Client,
    filename: str,
    offset: int,
    length: int,
    timeout: float = 30.0,
) -> bytes:
    """Download a byte range from a Common Crawl WARC file over HTTPS."""
    url = f"{WARC_HTTPS_PREFIX}{filename}"
    end = offset + length - 1
    headers = {"Range": f"bytes={offset}-{end}"}
    resp = client.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.content


# ── Shared parsing ──────────────────────────────────────────────────


def _extract_html_from_warc(raw: bytes) -> FetchedPage | None:
    """Parse a WARC record chunk and extract the HTML body.

    Returns None if the record is not a response or has no body.
    """
    try:
        stream = BytesIO(gzip.decompress(raw))
    except gzip.BadGzipFile:
        stream = BytesIO(raw)

    for warc_record in ArchiveIterator(stream):
        if warc_record.rec_type == "response":
            payload = warc_record.content_stream().read()
            # Split HTTP headers from body
            header_end = payload.find(b"\r\n\r\n")
            if header_end == -1:
                header_end = payload.find(b"\n\n")
            if header_end == -1:
                html = payload.decode("utf-8", errors="replace")
            else:
                html = payload[header_end + 4 :].decode("utf-8", errors="replace")
            return FetchedPage(
                record=CrawlRecord(url="", filename="", offset=0, length=0),
                html=html,
            )
    return None


# ── Page-level fetch (dispatches to backend) ────────────────────────


def fetch_page_s3(s3_client: object, record: CrawlRecord) -> FetchedPage | None:
    """Fetch a single page from Common Crawl S3 given its index record."""
    try:
        raw = _fetch_warc_range_s3(s3_client, record.filename, record.offset, record.length)
    except Exception:
        logger.warning("S3 fetch failed for %s", record.url)
        return None

    result = _extract_html_from_warc(raw)
    if result is None:
        return None
    result.record = record
    return result


def fetch_page_https(client: httpx.Client, record: CrawlRecord) -> FetchedPage | None:
    """Fetch a single page from Common Crawl HTTPS given its index record."""
    try:
        raw = _fetch_warc_range_https(client, record.filename, record.offset, record.length)
    except Exception:
        logger.warning("HTTPS fetch failed for %s", record.url)
        return None

    result = _extract_html_from_warc(raw)
    if result is None:
        return None
    result.record = record
    return result


# ── Batch fetcher ───────────────────────────────────────────────────


def _resolve_backend(backend: FetchBackend) -> FetchBackend:
    """Determine which backend to use when ``auto`` is specified."""
    if backend != FetchBackend.AUTO:
        return backend
    try:
        import boto3  # noqa: F401

        return FetchBackend.S3
    except ImportError:
        logger.info("boto3 not installed; falling back to HTTPS backend")
        return FetchBackend.HTTPS


def fetch_pages(
    records: Iterator[CrawlRecord],
    batch_size: int = 50,
    concurrency: int = 10,
    backend: FetchBackend = FetchBackend.AUTO,
) -> Iterator[FetchedPage]:
    """Fetch pages from Common Crawl in batches.

    Args:
        records: Iterator of CrawlRecords from the CC index.
        batch_size: Number of records to process per batch.
        concurrency: (reserved for future async implementation).
        backend: Which fetch backend to use (s3, https, or auto).
    """
    resolved = _resolve_backend(backend)
    logger.info("Using %s backend for WARC fetches", resolved.value)

    batch: list[CrawlRecord] = []

    if resolved == FetchBackend.S3:
        s3 = _get_s3_client()
        for rec in records:
            batch.append(rec)
            if len(batch) >= batch_size:
                yield from _process_batch_s3(s3, batch)
                batch = []
        if batch:
            yield from _process_batch_s3(s3, batch)
    else:
        with httpx.Client() as client:
            for rec in records:
                batch.append(rec)
                if len(batch) >= batch_size:
                    yield from _process_batch_https(client, batch)
                    batch = []
            if batch:
                yield from _process_batch_https(client, batch)


def _process_batch_s3(
    s3_client: object, batch: list[CrawlRecord]
) -> Iterator[FetchedPage]:
    """Process a batch of records via S3."""
    for rec in batch:
        page = fetch_page_s3(s3_client, rec)
        if page is not None and page.html.strip():
            logger.debug("Fetched %d bytes from %s (S3)", len(page.html), rec.url)
            yield page


def _process_batch_https(
    client: httpx.Client, batch: list[CrawlRecord]
) -> Iterator[FetchedPage]:
    """Process a batch of records via HTTPS."""
    for rec in batch:
        page = fetch_page_https(client, rec)
        if page is not None and page.html.strip():
            logger.debug("Fetched %d bytes from %s (HTTPS)", len(page.html), rec.url)
            yield page
