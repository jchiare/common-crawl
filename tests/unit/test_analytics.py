"""Tests for the analytics module."""

from fde_job_atlas.analytics.trends import AnalyticsEngine
from fde_job_atlas.models import JobPosting, RemoteType


def _make_postings() -> list[JobPosting]:
    return [
        JobPosting(
            url="https://a.com/1",
            title="Forward Deployed Engineer",
            company="Palantir",
            location="New York, NY",
            remote_type=RemoteType.HYBRID,
            skills=["python", "kubernetes", "aws"],
            fde_score=0.9,
            crawl_id="CC-MAIN-2024-10",
        ),
        JobPosting(
            url="https://b.com/2",
            title="Solutions Engineer",
            company="Palantir",
            location="San Francisco, CA",
            remote_type=RemoteType.REMOTE,
            skills=["python", "react", "sql"],
            fde_score=0.8,
            crawl_id="CC-MAIN-2024-10",
        ),
        JobPosting(
            url="https://c.com/3",
            title="Customer Engineer",
            company="Google",
            location="New York, NY",
            remote_type=RemoteType.ONSITE,
            skills=["python", "gcp", "terraform"],
            fde_score=0.85,
            crawl_id="CC-MAIN-2024-18",
        ),
        JobPosting(
            url="https://d.com/4",
            title="Backend Engineer",
            company="Stripe",
            location="San Francisco, CA",
            remote_type=RemoteType.REMOTE,
            skills=["go", "postgresql", "kubernetes"],
            fde_score=0.2,
            crawl_id="CC-MAIN-2024-18",
        ),
    ]


def test_skill_distribution():
    engine = AnalyticsEngine(_make_postings())
    dist = engine.skill_distribution()
    assert dist["python"] == 3
    assert dist["kubernetes"] == 2


def test_company_profiles():
    engine = AnalyticsEngine(_make_postings())
    profiles = engine.company_profiles()
    assert len(profiles) >= 3

    # Palantir should have 2 postings
    palantir = next(p for p in profiles if p.company == "Palantir")
    assert palantir.posting_count == 2


def test_trends_by_month():
    engine = AnalyticsEngine(_make_postings())
    trends = engine.trends_by_month()
    assert len(trends) >= 2

    # Should have entries for "2024-10" and "2024-18"
    periods = {t.period for t in trends}
    assert "2024-10" in periods
    assert "2024-18" in periods


def test_location_distribution():
    engine = AnalyticsEngine(_make_postings())
    dist = engine.location_distribution()
    assert dist["New York, NY"] == 2
    assert dist["San Francisco, CA"] == 2


def test_remote_distribution():
    engine = AnalyticsEngine(_make_postings())
    dist = engine.remote_distribution()
    assert dist["remote"] == 2
    assert dist["hybrid"] == 1
    assert dist["onsite"] == 1


def test_summary():
    engine = AnalyticsEngine(_make_postings())
    summary = engine.summary()
    assert summary["total_postings"] == 4
    assert summary["unique_companies"] == 3
    assert "python" in summary["top_skills"]
    assert summary["fde_score_stats"]["above_threshold"] == 3


def test_skill_clusters():
    engine = AnalyticsEngine(_make_postings())
    clusters = engine.skill_clusters()
    assert len(clusters) >= 2
    assert all(c.posting_count > 0 for c in clusters)


def test_empty_analytics():
    engine = AnalyticsEngine([])
    summary = engine.summary()
    assert summary["total_postings"] == 0
    assert summary["unique_companies"] == 0
