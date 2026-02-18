"""Query the Common Crawl URL index (cdx-api) for candidate job pages.

The CC index is a CDX-style API that lets us search URLs without downloading
the full crawl.  We look for career-page URL patterns and known ATS domains.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterator

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from fde_job_atlas.models import CrawlRecord

logger = logging.getLogger(__name__)

CDX_API = "https://index.commoncrawl.org/{crawl_id}-index"

# URL path patterns that strongly signal career / job pages
PATH_PATTERNS: list[str] = [
    "/careers",
    "/jobs",
    "/positions",
    "/role",
    "/apply",
    "/job/",
    "/opening",
    "/vacancies",
]

# Known ATS domains whose pages are almost always job postings
ATS_DOMAINS: list[str] = [
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "myworkdayjobs.com",
    "jobs.lever.co",
    "boards.greenhouse.io",
    "jobs.ashby.com",
    "icims.com",
    "smartrecruiters.com",
    "jobvite.com",
    "ultipro.com",
    "breezy.hr",
]

# Keywords that hint at FDE-style roles (used as URL / text filter)
FDE_KEYWORDS: list[str] = [
    "forward deployed",
    "field engineer",
    "solutions engineer",
    "customer engineer",
    "implementation engineer",
    "technical account",
    "professional services",
    "deployment engineer",
    "applied engineer",
    "partner engineer",
]


@dataclass
class IndexQueryConfig:
    """Parameters for a CC index query."""

    crawl_ids: list[str] = field(default_factory=lambda: ["CC-MAIN-2024-10"])
    max_pages: int = 100
    timeout: float = 30.0


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
def _fetch_index_page(
    client: httpx.Client,
    url: str,
    params: dict[str, str],
    timeout: float,
) -> list[dict[str, str]]:
    """Fetch a single page from the CDX index API."""
    resp = client.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    records: list[dict[str, str]] = []
    for line in lines:
        parts = line.split(" ", 2)
        if len(parts) < 3:
            continue
        # CDX format: urlkey timestamp json
        import json

        try:
            data = json.loads(parts[2])
            records.append(data)
        except json.JSONDecodeError:
            continue
    return records


def _record_from_cdx(data: dict[str, str], crawl_id: str) -> CrawlRecord | None:
    """Convert a CDX JSON blob into a CrawlRecord."""
    try:
        return CrawlRecord(
            url=data.get("url", ""),
            filename=data.get("filename", ""),
            offset=int(data.get("offset", 0)),
            length=int(data.get("length", 0)),
            status=int(data.get("status", 200)),
            mime=data.get("mime", "text/html"),
            crawl_id=crawl_id,
            timestamp=data.get("timestamp", ""),
        )
    except (ValueError, TypeError):
        return None


def _build_queries() -> list[str]:
    """Build search URL patterns for the CDX API.

    Returns wildcard-style URL queries that match career pages
    on arbitrary domains plus known ATS domains.
    """
    queries: list[str] = []
    # ATS domain queries (e.g. "*.greenhouse.io/*)
    for domain in ATS_DOMAINS:
        queries.append(f"*.{domain}/*")
    # Generic path-pattern queries
    for path in PATH_PATTERNS:
        queries.append(f"*{path}*")
    return queries


def query_index(config: IndexQueryConfig | None = None) -> Iterator[CrawlRecord]:
    """Yield CrawlRecords from the Common Crawl index matching job-page heuristics.

    This is the primary entry point for the discovery stage.
    """
    cfg = config or IndexQueryConfig()
    queries = _build_queries()

    with httpx.Client() as client:
        for crawl_id in cfg.crawl_ids:
            api_url = CDX_API.format(crawl_id=crawl_id)
            for q in queries:
                logger.info("Querying CC index: crawl=%s query=%s", crawl_id, q)
                page = 0
                while page < cfg.max_pages:
                    params = {
                        "url": q,
                        "output": "json",
                        "page": str(page),
                        "filter": "=status:200",
                        "fl": "url,filename,offset,length,status,mime,timestamp",
                    }
                    try:
                        rows = _fetch_index_page(client, api_url, params, cfg.timeout)
                    except Exception:
                        logger.warning(
                            "Failed to fetch index page %d for query %s", page, q
                        )
                        break

                    if not rows:
                        break

                    for row in rows:
                        rec = _record_from_cdx(row, crawl_id)
                        if rec and rec.url and rec.status == 200:
                            yield rec
                    page += 1


def filter_fde_candidates(records: Iterator[CrawlRecord]) -> Iterator[CrawlRecord]:
    """Post-filter index results to keep only URLs hinting at FDE roles.

    We do a lightweight URL-text check here; deeper content analysis
    happens after HTML fetch.
    """
    for rec in records:
        url_lower = rec.url.lower()
        for kw in FDE_KEYWORDS:
            if kw.replace(" ", "-") in url_lower or kw.replace(" ", "_") in url_lower:
                yield rec
                break
        else:
            # Also yield ATS domain pages (we'll classify later)
            for ats in ATS_DOMAINS:
                if ats in url_lower:
                    yield rec
                    break
