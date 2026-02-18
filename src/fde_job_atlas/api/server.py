"""FastAPI server for the FDE Job Atlas search + alerts API.

Endpoints:
  GET  /search          — semantic search over job postings
  GET  /postings/{id}   — get a single posting by ID
  POST /alerts          — create a saved-query alert
  GET  /alerts          — list alerts
  POST /alerts/check    — run all alerts and return new matches
  GET  /analytics       — get analytics summary
  GET  /analytics/skills — skill distribution
  GET  /analytics/companies — company profiles
  GET  /analytics/trends — time-series trends
  GET  /health          — health check
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from fde_job_atlas.analytics.trends import AnalyticsEngine
from fde_job_atlas.classifier.fde_classifier import FDEClassifier
from fde_job_atlas.models import Alert, JobPosting, SearchQuery, SearchResult
from fde_job_atlas.search.vector_search import VectorIndex

logger = logging.getLogger(__name__)

app = FastAPI(
    title="FDE Job Atlas",
    description="Semantic search engine for Forward Deployed Engineer job postings",
    version="0.1.0",
)

# ── Global state (initialized on startup) ───────────────────────────

_index: Optional[VectorIndex] = None
_classifier: Optional[FDEClassifier] = None


def get_index() -> VectorIndex:
    global _index
    if _index is None:
        _index = VectorIndex()
        _index.load_postings()
        _index._ensure_index()
    return _index


def get_classifier() -> FDEClassifier:
    global _classifier
    if _classifier is None:
        _classifier = FDEClassifier()
    return _classifier


# ── Request / Response models ────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str
    top_k: int = 20
    remote_type: Optional[str] = None
    location: Optional[str] = None
    company: Optional[str] = None
    seniority: Optional[str] = None
    min_fde_score: float = 0.0


class SearchResponse(BaseModel):
    results: list[dict]
    total: int
    query: str


class AlertRequest(BaseModel):
    query: str
    top_k: int = 10
    filters: dict[str, str] = {}


class AlertResponse(BaseModel):
    alert_id: str
    query: str
    created_at: str


# ── Endpoints ────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    idx = get_index()
    return {
        "status": "ok",
        "postings_loaded": len(idx._postings),
        "index_size": idx._index.ntotal if idx._index else 0,
    }


@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query text"),
    top_k: int = Query(20, ge=1, le=100),
    remote_type: Optional[str] = None,
    location: Optional[str] = None,
    company: Optional[str] = None,
    seniority: Optional[str] = None,
    min_fde_score: float = Query(0.0, ge=0.0, le=1.0),
) -> SearchResponse:
    """Semantic search over job postings."""
    idx = get_index()
    clf = get_classifier()

    filters: dict[str, str | list[str]] = {}
    if remote_type:
        filters["remote_type"] = remote_type
    if location:
        filters["location"] = location
    if company:
        filters["company"] = company
    if seniority:
        filters["seniority"] = seniority

    sq = SearchQuery(text=q, filters=filters, top_k=top_k)
    results = idx.search(sq, embed_fn=clf.embed_text)

    # Apply min FDE score filter
    if min_fde_score > 0:
        results = [r for r in results if r.posting.fde_score >= min_fde_score]

    return SearchResponse(
        results=[
            {
                "posting_id": r.posting.posting_id,
                "title": r.posting.title,
                "company": r.posting.company,
                "location": r.posting.location,
                "remote_type": r.posting.remote_type.value,
                "fde_score": r.posting.fde_score,
                "fde_label": r.posting.fde_label,
                "seniority": r.posting.seniority.value,
                "url": r.posting.url,
                "similarity_score": round(r.score, 4),
                "skills": r.posting.skills,
                "compensation": r.posting.compensation,
            }
            for r in results
        ],
        total=len(results),
        query=q,
    )


@app.get("/postings/{posting_id}")
def get_posting(posting_id: str) -> dict:
    """Get a single posting by its ID."""
    idx = get_index()
    for p in idx._postings:
        if p.posting_id == posting_id:
            return p.model_dump(exclude={"embedding"})
    raise HTTPException(status_code=404, detail="Posting not found")


@app.post("/alerts", response_model=AlertResponse)
def create_alert(req: AlertRequest) -> AlertResponse:
    """Create a saved-query alert."""
    idx = get_index()
    alert_id = uuid4().hex[:12]
    now = datetime.utcnow()

    alert = Alert(
        alert_id=alert_id,
        query=SearchQuery(text=req.query, filters=req.filters, top_k=req.top_k),
        created_at=now,
    )
    idx.add_alert(alert)

    return AlertResponse(
        alert_id=alert_id,
        query=req.query,
        created_at=now.isoformat(),
    )


@app.get("/alerts")
def list_alerts() -> list[dict]:
    """List all saved alerts."""
    idx = get_index()
    return [
        {
            "alert_id": a.alert_id,
            "query": a.query.text,
            "filters": a.query.filters,
            "created_at": a.created_at.isoformat(),
            "last_checked": a.last_checked.isoformat() if a.last_checked else None,
        }
        for a in idx._alerts
    ]


@app.post("/alerts/check")
def check_alerts() -> dict:
    """Run all alerts and return new matches."""
    idx = get_index()
    clf = get_classifier()
    triggered = idx.check_alerts(embed_fn=clf.embed_text)

    return {
        alert_id: [
            {
                "title": r.posting.title,
                "company": r.posting.company,
                "url": r.posting.url,
                "fde_score": r.posting.fde_score,
                "score": round(r.score, 4),
            }
            for r in results
        ]
        for alert_id, results in triggered.items()
    }


@app.get("/analytics")
def analytics_summary() -> dict:
    """Get full analytics summary."""
    idx = get_index()
    engine = AnalyticsEngine(idx._postings)
    return engine.summary()


@app.get("/analytics/skills")
def analytics_skills() -> dict:
    """Skill distribution across postings."""
    idx = get_index()
    engine = AnalyticsEngine(idx._postings)
    return {"skills": dict(engine.skill_distribution().most_common(50))}


@app.get("/analytics/companies")
def analytics_companies() -> list[dict]:
    """Company hiring profiles."""
    idx = get_index()
    engine = AnalyticsEngine(idx._postings)
    profiles = engine.company_profiles()
    return [
        {
            "company": p.company,
            "posting_count": p.posting_count,
            "roles": p.roles[:10],
            "avg_fde_score": p.avg_fde_score,
            "locations": p.locations,
            "top_skills": p.top_skills,
        }
        for p in profiles[:50]
    ]


@app.get("/analytics/trends")
def analytics_trends() -> list[dict]:
    """Time-series trends by crawl month."""
    idx = get_index()
    engine = AnalyticsEngine(idx._postings)
    trends = engine.trends_by_month()
    return [
        {
            "period": t.period,
            "count": t.count,
            "top_companies": t.top_companies,
            "top_skills": t.top_skills,
        }
        for t in trends
    ]
