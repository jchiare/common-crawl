"""Extract structured job data from HTML pages.

Strategy:
  1. Try JSON-LD JobPosting structured data first (most reliable).
  2. Fall back to heuristic DOM / text extraction.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from fde_job_atlas.models import (
    EmploymentType,
    JobPosting,
    RemoteType,
    Seniority,
)

logger = logging.getLogger(__name__)

# ── JSON-LD extraction ──────────────────────────────────────────────


def _find_jsonld_job(soup: BeautifulSoup) -> dict | None:
    """Find the first JSON-LD JobPosting object in the page."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        found = _extract_job_from_jsonld(data)
        if found is not None:
            return found
    return None


def _extract_job_from_jsonld(data: object) -> dict | None:
    if isinstance(data, dict):
        t = data.get("@type", "")
        types = [t] if isinstance(t, str) else (t if isinstance(t, list) else [])
        if any(x.lower() == "jobposting" for x in types if isinstance(x, str)):
            return data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                result = _extract_job_from_jsonld(item)
                if result is not None:
                    return result
    elif isinstance(data, list):
        for item in data:
            result = _extract_job_from_jsonld(item)
            if result is not None:
                return result
    return None


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(val[:19], fmt).date()
        except ValueError:
            continue
    return None


def _safe_str(val: object) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        return val.get("name", "") or val.get("@value", "") or str(val)
    return str(val)


def _extract_from_jsonld(data: dict, url: str) -> JobPosting:
    """Build a JobPosting from a JSON-LD JobPosting dict."""
    # Location
    loc_data = data.get("jobLocation")
    location = ""
    if isinstance(loc_data, dict):
        addr = loc_data.get("address", {})
        if isinstance(addr, dict):
            parts = [
                addr.get("addressLocality", ""),
                addr.get("addressRegion", ""),
                addr.get("addressCountry", ""),
            ]
            location = ", ".join(p for p in parts if p)
        else:
            location = _safe_str(addr)
    elif isinstance(loc_data, list) and loc_data:
        location = _safe_str(loc_data[0])

    # Remote
    remote_type = RemoteType.UNKNOWN
    loc_type = data.get("jobLocationType", "")
    if isinstance(loc_type, str) and (
        "remote" in loc_type.lower() or "telecommute" in loc_type.lower()
    ):
        remote_type = RemoteType.REMOTE
    applicant_req = data.get("applicantLocationRequirements")
    if applicant_req:
        remote_type = RemoteType.REMOTE

    # Employment type
    emp_raw = _safe_str(data.get("employmentType")).lower()
    emp_map = {
        "full": EmploymentType.FULL_TIME,
        "part": EmploymentType.PART_TIME,
        "contract": EmploymentType.CONTRACT,
        "intern": EmploymentType.INTERNSHIP,
    }
    employment_type = EmploymentType.UNKNOWN
    for key, val in emp_map.items():
        if key in emp_raw:
            employment_type = val
            break

    # Compensation
    salary = data.get("baseSalary") or data.get("estimatedSalary")
    compensation = ""
    if isinstance(salary, dict):
        val_obj = salary.get("value", salary)
        if isinstance(val_obj, dict):
            min_v = val_obj.get("minValue", "")
            max_v = val_obj.get("maxValue", "")
            currency = salary.get("currency", "")
            if min_v and max_v:
                compensation = f"{currency} {min_v}-{max_v}".strip()
            elif val_obj.get("value"):
                compensation = f"{currency} {val_obj['value']}".strip()
        else:
            compensation = str(val_obj)

    # Hiring org
    org = data.get("hiringOrganization", {})
    company = _safe_str(org.get("name")) if isinstance(org, dict) else _safe_str(org)

    description_html = _safe_str(data.get("description"))
    # Strip HTML tags from description
    desc_soup = BeautifulSoup(description_html, "lxml")
    description = desc_soup.get_text(separator="\n", strip=True)

    return JobPosting(
        url=url,
        canonical_url=url,
        source_domain=urlparse(url).netloc,
        title=_safe_str(data.get("title")),
        company=company,
        location=location,
        remote_type=remote_type,
        description=description,
        compensation=compensation,
        employment_type=employment_type,
        posted_date=_parse_date(_safe_str(data.get("datePosted"))),
        apply_url=_safe_str(data.get("directApply") or data.get("url") or url),
    )


# ── Heuristic DOM extraction ────────────────────────────────────────

_TITLE_SELECTORS = [
    "h1.job-title",
    "h1.posting-title",
    'h1[data-testid="job-title"]',
    "h1.position-title",
    ".job-title h1",
    "h1",
]

_COMPANY_SELECTORS = [
    ".company-name",
    ".posting-company",
    '[data-testid="company-name"]',
    ".employer-name",
]


def _extract_heuristic(html: str, url: str) -> JobPosting:
    """Best-effort extraction using DOM heuristics."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator="\n", strip=True)

    # Title
    title = ""
    for sel in _TITLE_SELECTORS:
        el = soup.select_one(sel)
        if el:
            title = el.get_text(strip=True)
            break

    # Company
    company = ""
    for sel in _COMPANY_SELECTORS:
        el = soup.select_one(sel)
        if el:
            company = el.get_text(strip=True)
            break

    # Location - look for common patterns
    location = ""
    loc_el = soup.select_one(".location, .job-location, [data-testid='location']")
    if loc_el:
        location = loc_el.get_text(strip=True)

    # Remote type from text
    remote_type = RemoteType.UNKNOWN
    text_lower = text.lower()
    if "remote" in text_lower:
        if "hybrid" in text_lower:
            remote_type = RemoteType.HYBRID
        else:
            remote_type = RemoteType.REMOTE

    # Split description into sections
    responsibilities, requirements = _extract_sections(text)

    # Skills extraction
    skills = _extract_skills(text)

    return JobPosting(
        url=url,
        canonical_url=url,
        source_domain=urlparse(url).netloc,
        title=title,
        company=company,
        location=location,
        remote_type=remote_type,
        description=text[:5000],
        responsibilities=responsibilities,
        requirements=requirements,
        skills=skills,
    )


def _extract_sections(text: str) -> tuple[list[str], list[str]]:
    """Extract responsibilities and requirements sections from job text."""
    resp_pattern = re.compile(
        r"(?:responsibilities|what you.ll do|your role)[:\s]*\n(.*?)(?=\n\s*\n|\Z)",
        re.I | re.S,
    )
    req_pattern = re.compile(
        r"(?:requirements|qualifications|what we.re looking for)[:\s]*\n(.*?)(?=\n\s*\n|\Z)",
        re.I | re.S,
    )

    responsibilities: list[str] = []
    req_match = req_pattern.search(text)
    resp_match = resp_pattern.search(text)

    if resp_match:
        responsibilities = [
            line.strip().lstrip("•-*").strip()
            for line in resp_match.group(1).split("\n")
            if line.strip()
        ]

    requirements: list[str] = []
    if req_match:
        requirements = [
            line.strip().lstrip("•-*").strip()
            for line in req_match.group(1).split("\n")
            if line.strip()
        ]

    return responsibilities[:20], requirements[:20]


_COMMON_SKILLS = [
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "rust",
    "c\\+\\+",
    "sql",
    "kubernetes",
    "docker",
    "aws",
    "gcp",
    "azure",
    "terraform",
    "react",
    "node\\.js",
    "machine learning",
    "deep learning",
    "pytorch",
    "tensorflow",
    "spark",
    "kafka",
    "postgresql",
    "mongodb",
    "redis",
    "graphql",
    "rest api",
    "ci/cd",
    "linux",
    "git",
]


def _extract_skills(text: str) -> list[str]:
    """Extract mentioned skills from the job text."""
    text_lower = text.lower()
    found: list[str] = []
    for skill in _COMMON_SKILLS:
        if re.search(r"\b" + skill + r"\b", text_lower):
            # Use the clean version of the skill name
            clean = skill.replace("\\+", "+").replace("\\.", ".")
            found.append(clean)
    return found


# ── Seniority detection ──────────────────────────────────────────────

_SENIORITY_MAP: list[tuple[re.Pattern[str], Seniority]] = [
    (re.compile(r"\b(intern|internship)\b", re.I), Seniority.INTERN),
    (re.compile(r"\bjunior\b|\bentry.level\b|\bassociate\b", re.I), Seniority.JUNIOR),
    (re.compile(r"\bsenior\b|\bsr\.?\b", re.I), Seniority.SENIOR),
    (re.compile(r"\bstaff\b", re.I), Seniority.STAFF),
    (re.compile(r"\bprincipal\b|\bdistinguished\b", re.I), Seniority.PRINCIPAL),
    (re.compile(r"\bdirector\b", re.I), Seniority.DIRECTOR),
    (re.compile(r"\bvp\b|\bvice president\b", re.I), Seniority.VP),
]


def _detect_seniority(title: str) -> Seniority:
    for pattern, level in _SENIORITY_MAP:
        if pattern.search(title):
            return level
    return Seniority.MID  # default


# ── Public API ──────────────────────────────────────────────────────


def extract_job_posting(html: str, url: str) -> JobPosting | None:
    """Extract a structured JobPosting from raw HTML.

    Tries JSON-LD first, then falls back to heuristic DOM extraction.
    Returns None only if extraction completely fails.
    """
    soup = BeautifulSoup(html, "lxml")

    # Try JSON-LD (preferred)
    jsonld = _find_jsonld_job(soup)
    if jsonld:
        logger.debug("Extracting via JSON-LD for %s", url)
        posting = _extract_from_jsonld(jsonld, url)
    else:
        logger.debug("Falling back to heuristic extraction for %s", url)
        posting = _extract_heuristic(html, url)

    # Enrich with seniority
    if posting.title:
        posting.seniority = _detect_seniority(posting.title)

    # Skip if we got nothing useful
    if not posting.title and not posting.description:
        return None

    return posting
