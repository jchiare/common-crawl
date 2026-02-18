"""Shared data models for the FDE Job Atlas pipeline."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field


class RemoteType(str, Enum):
    ONSITE = "onsite"
    REMOTE = "remote"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    UNKNOWN = "unknown"


class Seniority(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    DIRECTOR = "director"
    VP = "vp"
    UNKNOWN = "unknown"


class CrawlRecord(BaseModel):
    """A record from the Common Crawl URL index pointing to a WARC segment."""

    url: str
    filename: str  # WARC file path in S3
    offset: int
    length: int
    status: int = 200
    mime: str = "text/html"
    crawl_id: str = ""  # e.g. "CC-MAIN-2024-10"
    timestamp: str = ""


class JobPosting(BaseModel):
    """Normalized job posting extracted from a web page."""

    # Identity
    url: str
    canonical_url: str = ""
    source_domain: str = ""

    # Core fields
    title: str = ""
    company: str = ""
    location: str = ""
    remote_type: RemoteType = RemoteType.UNKNOWN
    travel: str = ""
    team: str = ""
    seniority: Seniority = Seniority.UNKNOWN

    # Description
    description: str = ""
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)

    # Compensation
    compensation: str = ""

    # Metadata
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    posted_date: Optional[date] = None
    apply_url: str = ""
    crawl_date: Optional[datetime] = None
    crawl_id: str = ""

    # FDE classification
    fde_score: float = 0.0  # 0..1 relevance score
    fde_label: str = ""  # e.g. "forward_deployed", "solutions_engineer", etc.

    # Embedding
    embedding: Optional[list[float]] = None

    # Dedup
    content_hash: str = ""
    dedup_cluster_id: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def posting_id(self) -> str:
        """Deterministic ID based on URL."""
        return hashlib.sha256(self.url.encode()).hexdigest()[:16]


class SearchQuery(BaseModel):
    """A user's search request."""

    text: str
    filters: dict[str, str | list[str]] = Field(default_factory=dict)
    top_k: int = 20


class SearchResult(BaseModel):
    """A single search result."""

    posting: JobPosting
    score: float


class Alert(BaseModel):
    """A saved search alert."""

    alert_id: str
    query: SearchQuery
    created_at: datetime
    last_checked: Optional[datetime] = None
    last_crawl_date: Optional[datetime] = None


class PipelineConfig(BaseModel):
    """Configuration for the full pipeline run."""

    # Common Crawl settings
    crawl_ids: list[str] = Field(
        default_factory=lambda: ["CC-MAIN-2024-10"]
    )
    max_index_pages: int = 100

    # Fetcher settings
    fetch_backend: str = "auto"  # "s3", "https", or "auto"
    fetch_batch_size: int = 50
    fetch_concurrency: int = 10

    # Extraction settings
    llm_fallback: bool = False  # Whether to use LLM extraction as fallback

    # Classifier settings
    embedding_model: str = "all-MiniLM-L6-v2"
    fde_threshold: float = 0.5

    # Search settings
    faiss_index_path: str = "data/faiss.index"
    postings_store_path: str = "data/postings.jsonl"

    # Storage
    raw_html_dir: str = "data/raw_html"
    output_dir: str = "data/output"
