"""Pipeline orchestrator: runs the full discovery → fetch → extract → dedup → classify → index flow.

Each stage is independently runnable and the pipeline saves intermediate
results so it can be resumed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from fde_job_atlas.classifier.fde_classifier import FDEClassifier
from fde_job_atlas.dedup.deduplicator import Deduplicator
from fde_job_atlas.discovery.cc_index import (
    IndexQueryConfig,
    filter_fde_candidates,
    query_index,
)
from fde_job_atlas.extraction.detector import is_job_posting
from fde_job_atlas.extraction.extractor import extract_job_posting
from fde_job_atlas.fetcher.warc_fetcher import FetchBackend, FetchedPage, fetch_pages
from fde_job_atlas.models import CrawlRecord, JobPosting, PipelineConfig
from fde_job_atlas.search.vector_search import VectorIndex

logger = logging.getLogger(__name__)


def _save_records(records: list[CrawlRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(r.model_dump_json() + "\n")


def _load_records(path: Path) -> list[CrawlRecord]:
    if not path.exists():
        return []
    records = []
    with open(path) as f:
        for line in f:
            if line.strip():
                records.append(CrawlRecord.model_validate_json(line))
    return records


def _save_postings(postings: list[JobPosting], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for p in postings:
            data = p.model_dump(exclude={"embedding"})
            f.write(json.dumps(data, default=str) + "\n")


def _load_postings(path: Path) -> list[JobPosting]:
    if not path.exists():
        return []
    postings = []
    with open(path) as f:
        for line in f:
            if line.strip():
                postings.append(JobPosting.model_validate_json(line))
    return postings


class Pipeline:
    """Orchestrate the full FDE Job Atlas pipeline."""

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def stage_discover(self) -> list[CrawlRecord]:
        """Stage 1: Query Common Crawl index for candidate URLs."""
        logger.info("=== Stage 1: Discovery ===")
        output_path = self.output_dir / "discovery_records.jsonl"

        # Check for cached results
        cached = _load_records(output_path)
        if cached:
            logger.info("Loaded %d cached discovery records", len(cached))
            return cached

        index_config = IndexQueryConfig(
            crawl_ids=self.config.crawl_ids,
            max_pages=self.config.max_index_pages,
        )

        all_records = list(query_index(index_config))
        logger.info("Raw index results: %d records", len(all_records))

        # Filter for FDE candidates
        candidates = list(filter_fde_candidates(iter(all_records)))
        logger.info("FDE-filtered candidates: %d records", len(candidates))

        _save_records(candidates, output_path)
        return candidates

    def stage_fetch(self, records: list[CrawlRecord]) -> list[FetchedPage]:
        """Stage 2: Fetch HTML from WARC files."""
        logger.info("=== Stage 2: Fetch (%d records) ===", len(records))

        backend = FetchBackend(self.config.fetch_backend)

        pages: list[FetchedPage] = []
        for page in tqdm(
            fetch_pages(
                iter(records),
                batch_size=self.config.fetch_batch_size,
                concurrency=self.config.fetch_concurrency,
                backend=backend,
            ),
            desc="Fetching pages",
            total=len(records),
        ):
            pages.append(page)

            # Save raw HTML
            html_dir = Path(self.config.raw_html_dir)
            html_dir.mkdir(parents=True, exist_ok=True)
            safe_name = page.record.posting_id[:16] if hasattr(page.record, 'posting_id') else str(len(pages))
            html_path = html_dir / f"{safe_name}.html"
            html_path.write_text(page.html, encoding="utf-8")

        logger.info("Fetched %d pages", len(pages))
        return pages

    def stage_extract(self, pages: list[FetchedPage]) -> list[JobPosting]:
        """Stage 3: Detect job postings and extract structured data."""
        logger.info("=== Stage 3: Extract (%d pages) ===", len(pages))
        output_path = self.output_dir / "extracted_postings.jsonl"

        postings: list[JobPosting] = []
        for page in tqdm(pages, desc="Extracting"):
            # Detection
            is_job, confidence = is_job_posting(page.html)
            if not is_job:
                continue

            # Extraction
            posting = extract_job_posting(page.html, page.record.url)
            if posting is None:
                continue

            posting.crawl_id = page.record.crawl_id
            posting.crawl_date = datetime.utcnow()
            postings.append(posting)

        logger.info("Extracted %d job postings", len(postings))
        _save_postings(postings, output_path)
        return postings

    def stage_dedup(self, postings: list[JobPosting]) -> list[JobPosting]:
        """Stage 4: Deduplicate postings."""
        logger.info("=== Stage 4: Dedup (%d postings) ===", len(postings))
        output_path = self.output_dir / "deduped_postings.jsonl"

        deduper = Deduplicator(threshold=0.7)
        unique = deduper.deduplicate(postings)

        _save_postings(unique, output_path)
        return unique

    def stage_classify(self, postings: list[JobPosting]) -> list[JobPosting]:
        """Stage 5: Classify postings for FDE relevance."""
        logger.info("=== Stage 5: Classify (%d postings) ===", len(postings))
        output_path = self.output_dir / "classified_postings.jsonl"

        classifier = FDEClassifier(
            model_name=self.config.embedding_model,
            threshold=self.config.fde_threshold,
        )

        classified = classifier.classify_batch(postings)

        fde_count = sum(1 for p in classified if p.fde_score >= self.config.fde_threshold)
        logger.info(
            "Classification: %d/%d above FDE threshold (%.2f)",
            fde_count,
            len(classified),
            self.config.fde_threshold,
        )

        _save_postings(classified, output_path)
        return classified

    def stage_index(self, postings: list[JobPosting]) -> VectorIndex:
        """Stage 6: Build the vector search index."""
        logger.info("=== Stage 6: Index (%d postings) ===", len(postings))

        index = VectorIndex(
            index_path=self.config.faiss_index_path,
            postings_path=self.config.postings_store_path,
        )
        index.build_index(postings)
        index.save()

        logger.info("Index built and saved")
        return index

    def run(self) -> VectorIndex:
        """Run the full pipeline end-to-end."""
        logger.info("Starting FDE Job Atlas pipeline")
        start = datetime.utcnow()

        records = self.stage_discover()
        pages = self.stage_fetch(records)
        postings = self.stage_extract(pages)
        unique = self.stage_dedup(postings)
        classified = self.stage_classify(unique)
        index = self.stage_index(classified)

        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info("Pipeline complete in %.1fs", elapsed)
        return index
