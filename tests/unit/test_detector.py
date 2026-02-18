"""Tests for the job posting detector."""

from fde_job_atlas.extraction.detector import (
    count_job_section_matches,
    has_apply_button,
    has_jsonld_job_posting,
    is_job_posting,
)
from bs4 import BeautifulSoup


# ── Fixtures ─────────────────────────────────────────────────────────

JSONLD_JOB_HTML = """
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Forward Deployed Engineer",
  "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
  "jobLocation": {
    "@type": "Place",
    "address": {"@type": "PostalAddress", "addressLocality": "San Francisco"}
  },
  "description": "We are looking for a Forward Deployed Engineer to work with customers.",
  "datePosted": "2024-03-01"
}
</script>
</head>
<body>
<h1>Forward Deployed Engineer</h1>
<h2>Responsibilities</h2>
<p>Work with customers on-site.</p>
<h2>Requirements</h2>
<p>3+ years Python.</p>
<a href="/apply" class="apply-btn">Apply Now</a>
</body>
</html>
"""

BLOG_HTML = """
<html>
<head><title>Our Company Blog</title></head>
<body>
<h1>Why We Love Engineering</h1>
<p>This is a blog post about engineering culture at our company.</p>
<p>We talk about our values and team events.</p>
</body>
</html>
"""

LISTING_HTML = """
<html>
<head><title>Careers at Acme</title></head>
<body>
<h1>Open Positions</h1>
<ul>
  <li><a href="/jobs/1">Software Engineer</a></li>
  <li><a href="/jobs/2">Product Manager</a></li>
  <li><a href="/jobs/3">Data Scientist</a></li>
</ul>
</body>
</html>
"""

APPLY_BUTTON_HTML = """
<html>
<body>
<h1>Senior Software Engineer</h1>
<h2>About the role</h2>
<p>Build amazing software.</p>
<h2>Responsibilities</h2>
<p>Design and build systems.</p>
<h2>Requirements</h2>
<p>5+ years experience.</p>
<h2>Benefits</h2>
<p>Health insurance, 401k.</p>
<a href="https://apply.example.com" class="apply-button">Apply Now</a>
</body>
</html>
"""


# ── Tests ────────────────────────────────────────────────────────────


def test_jsonld_detection():
    soup = BeautifulSoup(JSONLD_JOB_HTML, "lxml")
    assert has_jsonld_job_posting(soup) is True


def test_jsonld_not_present():
    soup = BeautifulSoup(BLOG_HTML, "lxml")
    assert has_jsonld_job_posting(soup) is False


def test_apply_button_detected():
    soup = BeautifulSoup(APPLY_BUTTON_HTML, "lxml")
    assert has_apply_button(soup) is True


def test_no_apply_button():
    soup = BeautifulSoup(BLOG_HTML, "lxml")
    assert has_apply_button(soup) is False


def test_section_matches_job_page():
    text = "Responsibilities: Build things. Requirements: Python. Benefits: Insurance."
    assert count_job_section_matches(text) >= 3


def test_section_matches_blog():
    text = "This is a blog post about company culture and team events."
    assert count_job_section_matches(text) == 0


def test_is_job_posting_jsonld():
    is_job, confidence = is_job_posting(JSONLD_JOB_HTML)
    assert is_job is True
    assert confidence >= 0.6


def test_is_not_job_posting_blog():
    is_job, confidence = is_job_posting(BLOG_HTML)
    assert is_job is False
    assert confidence < 0.4


def test_is_job_posting_apply_button():
    is_job, confidence = is_job_posting(APPLY_BUTTON_HTML)
    assert is_job is True
    assert confidence >= 0.4


def test_jsonld_in_graph():
    """Test JSON-LD detection with @graph structure."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": "Careers"},
        {"@type": "JobPosting", "title": "Engineer"}
    ]}
    </script>
    </head><body></body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    assert has_jsonld_job_posting(soup) is True
