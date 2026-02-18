"""Vector-based semantic search over job postings using FAISS.

Supports:
  - Building + saving a FAISS index from embedded postings
  - Semantic queries ("FDE for LLM evals", "no travel", "customer + python")
  - Metadata filters (location, remote, seniority, company, date)
  - Alert-style saved queries
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from fde_job_atlas.models import Alert, JobPosting, SearchQuery, SearchResult

logger = logging.getLogger(__name__)


class VectorIndex:
    """FAISS-backed vector index for semantic job search."""

    def __init__(
        self,
        dimension: int = 384,  # all-MiniLM-L6-v2 output dim
        index_path: str = "data/faiss.index",
        postings_path: str = "data/postings.jsonl",
    ):
        self.dimension = dimension
        self.index_path = Path(index_path)
        self.postings_path = Path(postings_path)
        self._index = None
        self._postings: list[JobPosting] = []
        self._alerts: list[Alert] = []

    def _ensure_index(self) -> None:
        """Create or load the FAISS index."""
        if self._index is not None:
            return
        import faiss

        if self.index_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            logger.info("Loaded FAISS index from %s (%d vectors)", self.index_path, self._index.ntotal)
        else:
            self._index = faiss.IndexFlatIP(self.dimension)  # inner product (cosine on normalized vecs)
            logger.info("Created new FAISS index (dim=%d)", self.dimension)

    def load_postings(self) -> None:
        """Load postings from the JSONL store."""
        if not self.postings_path.exists():
            return
        self._postings = []
        with open(self.postings_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    self._postings.append(JobPosting.model_validate_json(line))
        logger.info("Loaded %d postings from %s", len(self._postings), self.postings_path)

    def build_index(self, postings: list[JobPosting]) -> None:
        """Build a FAISS index from a list of postings with embeddings."""
        import faiss

        embeddings = []
        indexed_postings = []

        for p in postings:
            if p.embedding is not None:
                embeddings.append(p.embedding)
                indexed_postings.append(p)

        if not embeddings:
            logger.warning("No embeddings found; index will be empty")
            self._index = faiss.IndexFlatIP(self.dimension)
            return

        matrix = np.array(embeddings, dtype=np.float32)
        # Normalize for cosine similarity via inner product
        faiss.normalize_L2(matrix)

        self._index = faiss.IndexFlatIP(self.dimension)
        self._index.add(matrix)
        self._postings = indexed_postings
        logger.info("Built FAISS index with %d vectors", self._index.ntotal)

    def save(self) -> None:
        """Persist the FAISS index and postings to disk."""
        import faiss

        self._ensure_index()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_path))

        self.postings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.postings_path, "w") as f:
            for p in self._postings:
                # Exclude embedding from JSONL to save space
                data = p.model_dump(exclude={"embedding"})
                f.write(json.dumps(data, default=str) + "\n")

        logger.info(
            "Saved index (%d vectors) to %s and %d postings to %s",
            self._index.ntotal,
            self.index_path,
            len(self._postings),
            self.postings_path,
        )

    def search(
        self,
        query: SearchQuery,
        embed_fn: Optional[callable] = None,  # type: ignore[type-arg]
    ) -> list[SearchResult]:
        """Perform semantic search with optional metadata filters.

        Args:
            query: The search query with text and filters.
            embed_fn: Function to embed the query text. If None, requires
                      the FAISS index to already be loaded.
        """
        self._ensure_index()
        if self._index is None or self._index.ntotal == 0:
            return []

        if embed_fn is None:
            logger.warning("No embed_fn provided; returning empty results")
            return []

        # Embed the query
        query_vec = np.array([embed_fn(query.text)], dtype=np.float32)

        import faiss

        faiss.normalize_L2(query_vec)

        # Search more than top_k to allow for post-filtering
        search_k = min(query.top_k * 3, self._index.ntotal)
        scores, indices = self._index.search(query_vec, search_k)

        results: list[SearchResult] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._postings):
                continue
            posting = self._postings[idx]

            # Apply metadata filters
            if not self._matches_filters(posting, query.filters):
                continue

            results.append(SearchResult(posting=posting, score=float(score)))
            if len(results) >= query.top_k:
                break

        return results

    def _matches_filters(
        self, posting: JobPosting, filters: dict[str, str | list[str]]
    ) -> bool:
        """Check if a posting matches the given metadata filters."""
        for key, value in filters.items():
            posting_val = getattr(posting, key, None)
            if posting_val is None:
                return False

            if isinstance(value, list):
                if str(posting_val).lower() not in [v.lower() for v in value]:
                    return False
            else:
                if str(posting_val).lower() != value.lower():
                    return False
        return True

    # ── Alerts ───────────────────────────────────────────────────────

    def add_alert(self, alert: Alert) -> None:
        """Register a saved-query alert."""
        self._alerts.append(alert)

    def check_alerts(
        self,
        embed_fn: Optional[callable] = None,  # type: ignore[type-arg]
    ) -> dict[str, list[SearchResult]]:
        """Run all alerts and return new matches since last check.

        Returns a dict mapping alert_id → list of new SearchResults.
        """
        triggered: dict[str, list[SearchResult]] = {}
        now = datetime.utcnow()

        for alert in self._alerts:
            results = self.search(alert.query, embed_fn)

            # Filter to postings newer than last check
            if alert.last_crawl_date:
                results = [
                    r
                    for r in results
                    if r.posting.crawl_date
                    and r.posting.crawl_date > alert.last_crawl_date
                ]

            if results:
                triggered[alert.alert_id] = results
            alert.last_checked = now

        return triggered
