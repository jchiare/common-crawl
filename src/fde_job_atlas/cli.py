"""CLI entry point for the FDE Job Atlas pipeline.

Usage:
    fde-atlas run          — run the full pipeline
    fde-atlas discover     — run only the CC index discovery stage
    fde-atlas search TEXT  — search the indexed postings
    fde-atlas serve        — start the API server
    fde-atlas analytics    — print analytics summary
"""

from __future__ import annotations

import json
import logging
import sys

import click

from fde_job_atlas.models import PipelineConfig


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def main(verbose: bool) -> None:
    """FDE Job Atlas — mine Common Crawl for Forward Deployed Engineer roles."""
    _setup_logging(verbose)


@main.command()
@click.option(
    "--crawl-id",
    multiple=True,
    default=["CC-MAIN-2024-10"],
    help="Common Crawl crawl ID(s) to query",
)
@click.option("--max-pages", default=100, help="Max index pages per query")
@click.option("--embedding-model", default="all-MiniLM-L6-v2", help="Embedding model")
@click.option("--fde-threshold", default=0.5, type=float, help="FDE score threshold")
@click.option("--output-dir", default="data/output", help="Output directory")
@click.option(
    "--fetch-backend",
    type=click.Choice(["s3", "https", "auto"]),
    default="auto",
    help="Backend for fetching WARC data (s3=boto3, https=httpx, auto=prefer s3)",
)
def run(
    crawl_id: tuple[str, ...],
    max_pages: int,
    embedding_model: str,
    fde_threshold: float,
    output_dir: str,
    fetch_backend: str,
) -> None:
    """Run the full pipeline: discover → fetch → extract → dedup → classify → index."""
    from fde_job_atlas.pipeline.runner import Pipeline

    config = PipelineConfig(
        crawl_ids=list(crawl_id),
        max_index_pages=max_pages,
        embedding_model=embedding_model,
        fde_threshold=fde_threshold,
        output_dir=output_dir,
        fetch_backend=fetch_backend,
    )
    pipeline = Pipeline(config)
    pipeline.run()


@main.command()
@click.option("--crawl-id", multiple=True, default=["CC-MAIN-2024-10"])
@click.option("--max-pages", default=10, help="Max index pages per query")
def discover(crawl_id: tuple[str, ...], max_pages: int) -> None:
    """Run only the Common Crawl index discovery stage."""
    from fde_job_atlas.discovery.cc_index import IndexQueryConfig, query_index

    config = IndexQueryConfig(crawl_ids=list(crawl_id), max_pages=max_pages)
    count = 0
    for record in query_index(config):
        click.echo(f"{record.url}")
        count += 1
    click.echo(f"\nFound {count} candidate URLs")


@main.command()
@click.argument("text")
@click.option("--top-k", default=10, help="Number of results")
@click.option("--min-fde-score", default=0.0, type=float, help="Minimum FDE score")
def search(text: str, top_k: int, min_fde_score: float) -> None:
    """Search indexed job postings."""
    from fde_job_atlas.classifier.fde_classifier import FDEClassifier
    from fde_job_atlas.models import SearchQuery
    from fde_job_atlas.search.vector_search import VectorIndex

    index = VectorIndex()
    index.load_postings()
    index._ensure_index()

    classifier = FDEClassifier()
    query = SearchQuery(text=text, top_k=top_k)
    results = index.search(query, embed_fn=classifier.embed_text)

    if min_fde_score > 0:
        results = [r for r in results if r.posting.fde_score >= min_fde_score]

    if not results:
        click.echo("No results found.")
        return

    for i, r in enumerate(results, 1):
        p = r.posting
        click.echo(f"\n{'─' * 60}")
        click.echo(f"  #{i}  {p.title}")
        click.echo(f"  Company:    {p.company}")
        click.echo(f"  Location:   {p.location}  ({p.remote_type.value})")
        click.echo(f"  FDE Score:  {p.fde_score:.3f}  ({p.fde_label})")
        click.echo(f"  Similarity: {r.score:.4f}")
        click.echo(f"  Skills:     {', '.join(p.skills[:8])}")
        click.echo(f"  URL:        {p.url}")


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, type=int, help="Port to bind to")
def serve(host: str, port: int) -> None:
    """Start the FastAPI API server."""
    import uvicorn

    click.echo(f"Starting FDE Job Atlas API on {host}:{port}")
    uvicorn.run("fde_job_atlas.api.server:app", host=host, port=port, reload=False)


@main.command()
def analytics() -> None:
    """Print analytics summary of indexed postings."""
    from fde_job_atlas.analytics.trends import AnalyticsEngine
    from fde_job_atlas.search.vector_search import VectorIndex

    index = VectorIndex()
    index.load_postings()

    if not index._postings:
        click.echo("No postings indexed yet. Run the pipeline first.")
        return

    engine = AnalyticsEngine(index._postings)
    summary = engine.summary()
    click.echo(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
