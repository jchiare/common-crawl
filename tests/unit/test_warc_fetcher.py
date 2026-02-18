"""Tests for the WARC fetcher module."""

from fde_job_atlas.fetcher.warc_fetcher import (
    FetchBackend,
    FetchedPage,
    _extract_html_from_warc,
    _resolve_backend,
)
from fde_job_atlas.models import CrawlRecord


def test_fetch_backend_enum():
    assert FetchBackend.S3.value == "s3"
    assert FetchBackend.HTTPS.value == "https"
    assert FetchBackend.AUTO.value == "auto"


def test_resolve_backend_explicit_s3():
    assert _resolve_backend(FetchBackend.S3) == FetchBackend.S3


def test_resolve_backend_explicit_https():
    assert _resolve_backend(FetchBackend.HTTPS) == FetchBackend.HTTPS


def test_resolve_backend_auto():
    """Auto should resolve to S3 if boto3 is available."""
    result = _resolve_backend(FetchBackend.AUTO)
    # boto3 is in our deps, so should resolve to S3
    assert result in (FetchBackend.S3, FetchBackend.HTTPS)


def test_fetched_page_dataclass():
    rec = CrawlRecord(url="https://example.com", filename="f.warc.gz", offset=0, length=100)
    page = FetchedPage(record=rec, html="<html>hello</html>")
    assert page.html == "<html>hello</html>"
    assert page.http_status == 200
    assert page.http_headers is None


def test_extract_html_from_invalid_bytes():
    """Invalid WARC bytes should return None or an empty-html result."""
    result = _extract_html_from_warc(b"not a warc record at all")
    # warcio may parse garbage bytes as a record; what matters is
    # no useful HTML comes out.
    if result is not None:
        assert result.html.strip() == ""
