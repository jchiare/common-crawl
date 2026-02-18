"""Deduplication and canonicalization of job postings.

Uses:
  - URL normalization (strip tracking params, normalize scheme)
  - Content hashing (SimHash via datasketch MinHash for near-dupes)
  - Cluster assignment for identical / near-identical postings
"""

from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from datasketch import MinHash, MinHashLSH

from fde_job_atlas.models import JobPosting

logger = logging.getLogger(__name__)

# URL query params to strip (tracking / session params)
_STRIP_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_content",
    "utm_term",
    "ref",
    "source",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "gh_jid",
    "gh_src",
    "src",
    "referrer",
}


def canonicalize_url(url: str) -> str:
    """Normalize a URL for dedup purposes.

    - Lowercases scheme + host
    - Strips tracking query params
    - Removes trailing slash
    - Removes fragments
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"

    # Filter query params
    qs = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {k: v for k, v in qs.items() if k.lower() not in _STRIP_PARAMS}
    query = urlencode(filtered, doseq=True)

    return urlunparse((scheme, host, path, "", query, ""))


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized text content."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    return hashlib.sha256(normalized.encode()).hexdigest()


def _text_shingles(text: str, k: int = 5) -> list[str]:
    """Generate character-level k-shingles from text."""
    normalized = re.sub(r"\s+", " ", text.lower().strip())
    if len(normalized) < k:
        return [normalized]
    return [normalized[i : i + k] for i in range(len(normalized) - k + 1)]


def build_minhash(text: str, num_perm: int = 128) -> MinHash:
    """Build a MinHash signature for near-duplicate detection."""
    mh = MinHash(num_perm=num_perm)
    for shingle in _text_shingles(text):
        mh.update(shingle.encode("utf-8"))
    return mh


class Deduplicator:
    """Deduplicate job postings using exact URL match + MinHash LSH."""

    def __init__(self, threshold: float = 0.7, num_perm: int = 128):
        self.threshold = threshold
        self.num_perm = num_perm
        self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self._seen_urls: set[str] = set()
        self._seen_hashes: set[str] = set()
        self._cluster_counter = 0
        self._key_to_cluster: dict[str, str] = {}

    def _next_cluster_id(self) -> str:
        self._cluster_counter += 1
        return f"cluster-{self._cluster_counter}"

    def deduplicate(self, postings: list[JobPosting]) -> list[JobPosting]:
        """Remove duplicate postings, returning unique ones with cluster IDs.

        Duplicates are detected via:
          1. Exact canonical URL match
          2. Exact content hash match
          3. MinHash LSH near-duplicate detection on description text
        """
        unique: list[JobPosting] = []

        for posting in postings:
            # Canonicalize URL
            canon = canonicalize_url(posting.url)
            posting.canonical_url = canon

            # 1. Exact URL dedup
            if canon in self._seen_urls:
                logger.debug("URL duplicate: %s", canon)
                continue
            self._seen_urls.add(canon)

            # 2. Exact content hash dedup
            c_hash = content_hash(posting.description)
            posting.content_hash = c_hash
            if c_hash in self._seen_hashes:
                logger.debug("Content-hash duplicate: %s", posting.url)
                continue
            self._seen_hashes.add(c_hash)

            # 3. MinHash LSH near-duplicate detection
            if posting.description:
                mh = build_minhash(posting.description, self.num_perm)
                key = posting.posting_id

                try:
                    neighbors = self.lsh.query(mh)
                except ValueError:
                    neighbors = []

                if neighbors:
                    # Assign to existing cluster
                    first_neighbor = neighbors[0]
                    cluster_id = self._key_to_cluster.get(
                        first_neighbor, self._next_cluster_id()
                    )
                    posting.dedup_cluster_id = cluster_id
                    logger.debug(
                        "Near-duplicate of %s: %s", first_neighbor, posting.url
                    )
                    continue

                # New unique posting
                cluster_id = self._next_cluster_id()
                posting.dedup_cluster_id = cluster_id
                self._key_to_cluster[key] = cluster_id
                try:
                    self.lsh.insert(key, mh)
                except ValueError:
                    pass  # duplicate key, skip

            unique.append(posting)

        logger.info(
            "Dedup: %d input → %d unique postings", len(postings), len(unique)
        )
        return unique
