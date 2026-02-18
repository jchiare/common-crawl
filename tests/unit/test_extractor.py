"""Tests for the structured job data extractor."""

from fde_job_atlas.extraction.extractor import extract_job_posting
from fde_job_atlas.models import RemoteType, Seniority


JSONLD_HTML = """
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "JobPosting",
  "title": "Senior Forward Deployed Engineer",
  "hiringOrganization": {"@type": "Organization", "name": "Palantir Technologies"},
  "jobLocation": {
    "@type": "Place",
    "address": {
      "@type": "PostalAddress",
      "addressLocality": "New York",
      "addressRegion": "NY",
      "addressCountry": "US"
    }
  },
  "description": "<p>Join our team as a Forward Deployed Engineer working with enterprise customers. You will deploy and integrate our platform. Requirements include Python, Kubernetes, and customer-facing experience.</p>",
  "datePosted": "2024-03-15",
  "employmentType": "FULL_TIME",
  "baseSalary": {
    "currency": "USD",
    "value": {"minValue": 150000, "maxValue": 250000}
  },
  "jobLocationType": "TELECOMMUTE"
}
</script>
</head>
<body>
<h1>Senior Forward Deployed Engineer</h1>
</body>
</html>
"""

HEURISTIC_HTML = """
<html>
<head><title>Solutions Engineer - Acme Corp</title></head>
<body>
<h1 class="job-title">Solutions Engineer</h1>
<div class="company-name">Acme Corp</div>
<div class="location">San Francisco, CA</div>
<h2>About the Role</h2>
<p>Work with enterprise customers in a hybrid remote setting.</p>
<h2>Responsibilities</h2>
<ul>
  <li>Build custom integrations for customers</li>
  <li>Conduct proof-of-concept demonstrations</li>
</ul>
<h2>Requirements</h2>
<ul>
  <li>3+ years Python experience</li>
  <li>Experience with kubernetes and docker</li>
  <li>Strong SQL skills</li>
</ul>
<a href="/apply">Apply Now</a>
</body>
</html>
"""

EMPTY_HTML = "<html><body></body></html>"


def test_jsonld_extraction():
    posting = extract_job_posting(JSONLD_HTML, "https://palantir.com/jobs/fde")
    assert posting is not None
    assert posting.title == "Senior Forward Deployed Engineer"
    assert posting.company == "Palantir Technologies"
    assert "New York" in posting.location
    assert posting.remote_type == RemoteType.REMOTE
    assert posting.seniority == Seniority.SENIOR
    assert "150000" in posting.compensation
    assert posting.posted_date is not None
    assert posting.posted_date.year == 2024


def test_heuristic_extraction():
    posting = extract_job_posting(HEURISTIC_HTML, "https://acme.com/jobs/se")
    assert posting is not None
    assert posting.title == "Solutions Engineer"
    assert posting.company == "Acme Corp"
    assert "python" in posting.skills
    assert "kubernetes" in posting.skills
    assert "sql" in posting.skills


def test_empty_html_returns_none():
    posting = extract_job_posting(EMPTY_HTML, "https://example.com")
    assert posting is None


def test_seniority_detection():
    """Various titles should map to correct seniority levels."""
    cases = [
        ("Junior Software Engineer", Seniority.JUNIOR),
        ("Senior Forward Deployed Engineer", Seniority.SENIOR),
        ("Staff Solutions Engineer", Seniority.STAFF),
        ("Principal Customer Engineer", Seniority.PRINCIPAL),
        ("Solutions Engineer", Seniority.MID),
        ("Engineering Intern", Seniority.INTERN),
    ]
    for title, expected in cases:
        html = f"<html><body><h1>{title}</h1><p>Description of role.</p></body></html>"
        posting = extract_job_posting(html, "https://example.com/job")
        assert posting is not None, f"Failed for title: {title}"
        assert posting.seniority == expected, f"Expected {expected} for '{title}', got {posting.seniority}"


def test_skills_extraction():
    html = """
    <html><body>
    <h1>Engineer</h1>
    <p>We need someone with Python, Docker, AWS, and PostgreSQL experience.
    Knowledge of React and GraphQL is a plus. Must know Git and Linux.</p>
    </body></html>
    """
    posting = extract_job_posting(html, "https://example.com/job")
    assert posting is not None
    assert "python" in posting.skills
    assert "docker" in posting.skills
    assert "aws" in posting.skills
    assert "react" in posting.skills
    assert "git" in posting.skills
