"""Detect whether a page is an actual job posting vs. a listing/blog/other.

Uses a combination of:
  1. JSON-LD ``JobPosting`` structured data (strongest signal)
  2. DOM heuristics (apply-button selectors, typical job-page structure)
  3. Text-pattern heuristics (sections like "Requirements", "Responsibilities")
"""

from __future__ import annotations

import json
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Text section headings common in job postings
_JOB_SECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(responsibilities|what you.ll do)\b", re.I),
    re.compile(r"\b(requirements|qualifications|what we.re looking for)\b", re.I),
    re.compile(r"\b(about the role|role overview|position summary)\b", re.I),
    re.compile(r"\b(benefits|perks|compensation)\b", re.I),
    re.compile(r"\b(apply now|submit.{0,10}application)\b", re.I),
]

# CSS selectors that signal an "Apply" button
_APPLY_SELECTORS: list[str] = [
    'a[href*="apply"]',
    'button[class*="apply"]',
    'a[class*="apply"]',
    'input[value*="Apply"]',
    'a[data-action*="apply"]',
]


def has_jsonld_job_posting(soup: BeautifulSoup) -> bool:
    """Check for schema.org JobPosting in JSON-LD blocks."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if _is_job_posting_jsonld(data):
            return True
    return False


def _is_job_posting_jsonld(data: object) -> bool:
    if isinstance(data, dict):
        t = data.get("@type", "")
        if isinstance(t, str) and t.lower() == "jobposting":
            return True
        if isinstance(t, list) and any(
            x.lower() == "jobposting" for x in t if isinstance(x, str)
        ):
            return True
        # Check @graph
        graph = data.get("@graph")
        if isinstance(graph, list):
            return any(_is_job_posting_jsonld(item) for item in graph)
    elif isinstance(data, list):
        return any(_is_job_posting_jsonld(item) for item in data)
    return False


def has_apply_button(soup: BeautifulSoup) -> bool:
    """Check for an Apply button/link in the DOM."""
    for sel in _APPLY_SELECTORS:
        if soup.select_one(sel):
            return True
    return False


def count_job_section_matches(text: str) -> int:
    """Count how many typical job-posting section headings appear in the text."""
    return sum(1 for pat in _JOB_SECTION_PATTERNS if pat.search(text))


def is_job_posting(html: str) -> tuple[bool, float]:
    """Determine whether an HTML page is a job posting.

    Returns (is_posting, confidence) where confidence is 0..1.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ", strip=True)[:10_000]  # cap for speed

    score = 0.0

    # JSON-LD is the strongest signal
    if has_jsonld_job_posting(soup):
        score += 0.6

    # Apply button
    if has_apply_button(soup):
        score += 0.2

    # Section headings
    section_hits = count_job_section_matches(text)
    score += min(section_hits * 0.08, 0.3)

    # Title tag heuristic
    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text().lower()
        job_title_words = ["career", "job", "position", "role", "opening", "hiring"]
        if any(w in title_text for w in job_title_words):
            score += 0.1

    confidence = min(score, 1.0)
    return confidence >= 0.4, confidence
