"""Tests for the shared data models."""

from datetime import date, datetime

from fde_job_atlas.models import (
    CrawlRecord,
    EmploymentType,
    JobPosting,
    PipelineConfig,
    RemoteType,
    SearchQuery,
    Seniority,
)


def test_job_posting_id_deterministic():
    """posting_id should be a deterministic hash of the URL."""
    p1 = JobPosting(url="https://example.com/jobs/123")
    p2 = JobPosting(url="https://example.com/jobs/123")
    p3 = JobPosting(url="https://example.com/jobs/456")

    assert p1.posting_id == p2.posting_id
    assert p1.posting_id != p3.posting_id
    assert len(p1.posting_id) == 16


def test_job_posting_defaults():
    p = JobPosting(url="https://example.com/job")
    assert p.remote_type == RemoteType.UNKNOWN
    assert p.seniority == Seniority.UNKNOWN
    assert p.employment_type == EmploymentType.UNKNOWN
    assert p.fde_score == 0.0
    assert p.embedding is None
    assert p.skills == []
    assert p.responsibilities == []


def test_crawl_record_creation():
    rec = CrawlRecord(
        url="https://example.com/careers",
        filename="crawl-data/CC-MAIN-2024-10/segments/123/warc/00000.warc.gz",
        offset=1000,
        length=5000,
        crawl_id="CC-MAIN-2024-10",
    )
    assert rec.status == 200
    assert rec.mime == "text/html"


def test_search_query_defaults():
    q = SearchQuery(text="FDE for LLM evals")
    assert q.top_k == 20
    assert q.filters == {}


def test_pipeline_config_defaults():
    cfg = PipelineConfig()
    assert cfg.crawl_ids == ["CC-MAIN-2024-10"]
    assert cfg.fetch_backend == "auto"
    assert cfg.fde_threshold == 0.5
    assert cfg.embedding_model == "all-MiniLM-L6-v2"


def test_pipeline_config_custom():
    cfg = PipelineConfig(
        crawl_ids=["CC-MAIN-2024-18", "CC-MAIN-2024-22"],
        fetch_backend="s3",
        fde_threshold=0.7,
    )
    assert len(cfg.crawl_ids) == 2
    assert cfg.fetch_backend == "s3"


def test_job_posting_serialization():
    """Test round-trip JSON serialization."""
    p = JobPosting(
        url="https://example.com/jobs/fde",
        title="Forward Deployed Engineer",
        company="Palantir",
        location="New York, NY",
        remote_type=RemoteType.HYBRID,
        seniority=Seniority.SENIOR,
        fde_score=0.92,
        skills=["python", "kubernetes"],
        posted_date=date(2024, 3, 15),
    )
    json_str = p.model_dump_json()
    restored = JobPosting.model_validate_json(json_str)
    assert restored.title == "Forward Deployed Engineer"
    assert restored.company == "Palantir"
    assert restored.remote_type == RemoteType.HYBRID
    assert restored.fde_score == 0.92
    assert restored.skills == ["python", "kubernetes"]
