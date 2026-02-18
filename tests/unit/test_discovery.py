"""Tests for the Common Crawl index discovery module."""

from fde_job_atlas.discovery.cc_index import (
    ATS_DOMAINS,
    FDE_KEYWORDS,
    PATH_PATTERNS,
    _build_queries,
    _record_from_cdx,
    filter_fde_candidates,
)
from fde_job_atlas.models import CrawlRecord


def test_build_queries():
    """Should generate queries for ATS domains and path patterns."""
    queries = _build_queries()
    assert len(queries) > 0
    # Should include ATS domain queries
    assert any("greenhouse.io" in q for q in queries)
    assert any("lever.co" in q for q in queries)
    # Should include path pattern queries
    assert any("/careers" in q for q in queries)
    assert any("/jobs" in q for q in queries)


def test_record_from_cdx_valid():
    data = {
        "url": "https://boards.greenhouse.io/company/jobs/123",
        "filename": "crawl-data/CC-MAIN-2024-10/segments/1.warc.gz",
        "offset": "1000",
        "length": "5000",
        "status": "200",
        "mime": "text/html",
        "timestamp": "20240315120000",
    }
    rec = _record_from_cdx(data, "CC-MAIN-2024-10")
    assert rec is not None
    assert rec.url == data["url"]
    assert rec.offset == 1000
    assert rec.length == 5000
    assert rec.crawl_id == "CC-MAIN-2024-10"


def test_record_from_cdx_invalid():
    data = {"url": "https://example.com", "offset": "not_a_number"}
    rec = _record_from_cdx(data, "CC-MAIN-2024-10")
    assert rec is None


def test_filter_fde_candidates_keyword_match():
    """Records with FDE keywords in URL should pass the filter."""
    records = [
        CrawlRecord(
            url="https://example.com/careers/forward-deployed-engineer",
            filename="f.warc.gz",
            offset=0,
            length=100,
        ),
        CrawlRecord(
            url="https://example.com/blog/about-us",
            filename="f.warc.gz",
            offset=0,
            length=100,
        ),
    ]
    filtered = list(filter_fde_candidates(iter(records)))
    assert len(filtered) == 1
    assert "forward-deployed" in filtered[0].url


def test_filter_fde_candidates_ats_domain():
    """Records from ATS domains should pass the filter."""
    records = [
        CrawlRecord(
            url="https://boards.greenhouse.io/company/jobs/456",
            filename="f.warc.gz",
            offset=0,
            length=100,
        ),
    ]
    filtered = list(filter_fde_candidates(iter(records)))
    assert len(filtered) == 1


def test_filter_fde_candidates_no_match():
    """Records without FDE signals should be filtered out."""
    records = [
        CrawlRecord(
            url="https://example.com/about",
            filename="f.warc.gz",
            offset=0,
            length=100,
        ),
    ]
    filtered = list(filter_fde_candidates(iter(records)))
    assert len(filtered) == 0


def test_path_patterns_cover_common_paths():
    expected = ["/careers", "/jobs", "/positions"]
    for path in expected:
        assert path in PATH_PATTERNS


def test_ats_domains_cover_major_platforms():
    expected = ["greenhouse.io", "lever.co", "ashbyhq.com"]
    for domain in expected:
        assert domain in ATS_DOMAINS
