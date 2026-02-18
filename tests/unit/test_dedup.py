"""Tests for the deduplication module."""

from fde_job_atlas.dedup.deduplicator import (
    Deduplicator,
    build_minhash,
    canonicalize_url,
    content_hash,
)
from fde_job_atlas.models import JobPosting


def test_canonicalize_strips_tracking_params():
    url = "https://Example.Com/jobs/123?utm_source=twitter&utm_medium=social&ref=homepage"
    canon = canonicalize_url(url)
    assert "utm_source" not in canon
    assert "utm_medium" not in canon
    assert "ref" not in canon
    assert "example.com" in canon


def test_canonicalize_lowercases_host():
    url = "HTTPS://WWW.EXAMPLE.COM/Jobs/FDE/"
    canon = canonicalize_url(url)
    assert canon.startswith("https://www.example.com")


def test_canonicalize_removes_trailing_slash():
    url = "https://example.com/jobs/123/"
    canon = canonicalize_url(url)
    assert not canon.endswith("/") or canon.endswith(".com/")


def test_canonicalize_preserves_meaningful_params():
    url = "https://example.com/jobs?id=123&department=engineering"
    canon = canonicalize_url(url)
    assert "id=123" in canon
    assert "department=engineering" in canon


def test_content_hash_deterministic():
    text = "Forward Deployed Engineer at Palantir"
    h1 = content_hash(text)
    h2 = content_hash(text)
    assert h1 == h2


def test_content_hash_whitespace_invariant():
    h1 = content_hash("hello  world")
    h2 = content_hash("hello world")
    assert h1 == h2


def test_content_hash_case_invariant():
    h1 = content_hash("Forward Deployed")
    h2 = content_hash("forward deployed")
    assert h1 == h2


def test_minhash_similar_texts():
    """Similar texts should produce similar MinHash signatures."""
    t1 = "Forward Deployed Engineer working with enterprise customers on software deployment"
    t2 = "Forward Deployed Engineer working with enterprise clients on software deployment"

    mh1 = build_minhash(t1)
    mh2 = build_minhash(t2)
    similarity = mh1.jaccard(mh2)
    assert similarity > 0.5  # Similar texts should have high Jaccard


def test_minhash_different_texts():
    """Very different texts should have low MinHash similarity."""
    t1 = "Forward Deployed Engineer working with enterprise customers"
    t2 = "Marketing Manager for digital advertising campaigns targeting new markets"

    mh1 = build_minhash(t1)
    mh2 = build_minhash(t2)
    similarity = mh1.jaccard(mh2)
    assert similarity < 0.5


def test_deduplicator_exact_url():
    """Exact URL duplicates should be removed."""
    deduper = Deduplicator()
    postings = [
        JobPosting(url="https://example.com/jobs/1", title="FDE", description="Desc A"),
        JobPosting(url="https://example.com/jobs/1", title="FDE", description="Desc A"),
    ]
    unique = deduper.deduplicate(postings)
    assert len(unique) == 1


def test_deduplicator_content_hash():
    """Same content at different URLs should be deduped."""
    deduper = Deduplicator()
    desc = "Forward Deployed Engineer role at our company. Work with customers."
    postings = [
        JobPosting(url="https://a.com/job/1", title="FDE", description=desc),
        JobPosting(url="https://b.com/job/1", title="FDE", description=desc),
    ]
    unique = deduper.deduplicate(postings)
    assert len(unique) == 1


def test_deduplicator_different_content():
    """Different postings should not be deduped."""
    deduper = Deduplicator()
    postings = [
        JobPosting(
            url="https://a.com/job/1",
            title="Forward Deployed Engineer",
            description="Work with customers on deploying enterprise software solutions on-site.",
        ),
        JobPosting(
            url="https://b.com/job/2",
            title="Backend Software Engineer",
            description="Build scalable distributed systems and microservices architecture.",
        ),
    ]
    unique = deduper.deduplicate(postings)
    assert len(unique) == 2


def test_deduplicator_url_normalization():
    """URLs with tracking params should be normalized before dedup."""
    deduper = Deduplicator()
    postings = [
        JobPosting(
            url="https://example.com/jobs/123?utm_source=linkedin",
            title="FDE",
            description="A unique description alpha.",
        ),
        JobPosting(
            url="https://example.com/jobs/123?utm_source=twitter",
            title="FDE",
            description="A unique description beta.",
        ),
    ]
    unique = deduper.deduplicate(postings)
    assert len(unique) == 1  # Same canonical URL
