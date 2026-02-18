"""Analytics and trends over collected job postings.

Provides:
  - Skill clustering (group postings by dominant skills)
  - Company hiring profiles
  - Trend analysis over time (by crawl month)
  - Geographic distribution
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from fde_job_atlas.models import JobPosting

logger = logging.getLogger(__name__)


@dataclass
class SkillCluster:
    """A group of postings sharing a common skill profile."""

    name: str
    skills: list[str]
    posting_count: int
    example_titles: list[str] = field(default_factory=list)


@dataclass
class CompanyProfile:
    """Hiring profile for a single company."""

    company: str
    posting_count: int
    roles: list[str]
    avg_fde_score: float
    locations: list[str]
    top_skills: list[str]


@dataclass
class TrendPoint:
    """A data point for time-series trends."""

    period: str  # e.g. "2024-03"
    count: int
    top_companies: list[str]
    top_skills: list[str]


class AnalyticsEngine:
    """Compute analytics from a collection of job postings."""

    def __init__(self, postings: list[JobPosting] | None = None):
        self.postings = postings or []

    def skill_distribution(self) -> Counter:
        """Count skill mentions across all postings."""
        counter: Counter = Counter()
        for p in self.postings:
            for skill in p.skills:
                counter[skill] += 1
        return counter

    def skill_clusters(self) -> list[SkillCluster]:
        """Group postings into skill-based clusters.

        Uses a simple co-occurrence heuristic: postings are grouped
        by their dominant skill (most mentioned skill set).
        """
        # Group postings by their primary skill (first listed or most common)
        clusters_map: dict[str, list[JobPosting]] = defaultdict(list)

        for p in self.postings:
            if p.skills:
                primary = p.skills[0]  # Use first skill as cluster key
                clusters_map[primary].append(p)
            else:
                clusters_map["unclassified"].append(p)

        clusters: list[SkillCluster] = []
        for skill, posts in sorted(
            clusters_map.items(), key=lambda x: -len(x[1])
        ):
            all_skills: Counter = Counter()
            for p in posts:
                all_skills.update(p.skills)

            clusters.append(
                SkillCluster(
                    name=f"{skill}-focused",
                    skills=[s for s, _ in all_skills.most_common(10)],
                    posting_count=len(posts),
                    example_titles=[p.title for p in posts[:5] if p.title],
                )
            )

        return clusters

    def company_profiles(self) -> list[CompanyProfile]:
        """Build hiring profiles per company."""
        by_company: dict[str, list[JobPosting]] = defaultdict(list)
        for p in self.postings:
            if p.company:
                by_company[p.company].append(p)

        profiles: list[CompanyProfile] = []
        for company, posts in sorted(
            by_company.items(), key=lambda x: -len(x[1])
        ):
            skills: Counter = Counter()
            locations: Counter = Counter()
            for p in posts:
                skills.update(p.skills)
                if p.location:
                    locations[p.location] += 1

            avg_score = (
                sum(p.fde_score for p in posts) / len(posts) if posts else 0
            )

            profiles.append(
                CompanyProfile(
                    company=company,
                    posting_count=len(posts),
                    roles=list({p.title for p in posts if p.title}),
                    avg_fde_score=round(avg_score, 3),
                    locations=[loc for loc, _ in locations.most_common(5)],
                    top_skills=[s for s, _ in skills.most_common(10)],
                )
            )

        return profiles

    def trends_by_month(self) -> list[TrendPoint]:
        """Compute posting counts and top signals per crawl month."""
        by_month: dict[str, list[JobPosting]] = defaultdict(list)

        for p in self.postings:
            if p.crawl_date:
                period = p.crawl_date.strftime("%Y-%m")
            elif p.crawl_id:
                # Extract month from crawl_id like "CC-MAIN-2024-10"
                parts = p.crawl_id.split("-")
                if len(parts) >= 4:
                    period = f"{parts[2]}-{parts[3]}"
                else:
                    period = "unknown"
            else:
                period = "unknown"
            by_month[period].append(p)

        trends: list[TrendPoint] = []
        for period in sorted(by_month.keys()):
            posts = by_month[period]
            companies: Counter = Counter()
            skills: Counter = Counter()
            for p in posts:
                if p.company:
                    companies[p.company] += 1
                skills.update(p.skills)

            trends.append(
                TrendPoint(
                    period=period,
                    count=len(posts),
                    top_companies=[c for c, _ in companies.most_common(5)],
                    top_skills=[s for s, _ in skills.most_common(10)],
                )
            )

        return trends

    def location_distribution(self) -> Counter:
        """Count postings by location."""
        counter: Counter = Counter()
        for p in self.postings:
            if p.location:
                counter[p.location] += 1
            else:
                counter["Unknown"] += 1
        return counter

    def remote_distribution(self) -> Counter:
        """Count postings by remote type."""
        counter: Counter = Counter()
        for p in self.postings:
            counter[p.remote_type.value] += 1
        return counter

    def summary(self) -> dict:
        """Generate a full analytics summary."""
        skill_dist = self.skill_distribution()
        loc_dist = self.location_distribution()
        remote_dist = self.remote_distribution()

        return {
            "total_postings": len(self.postings),
            "unique_companies": len({p.company for p in self.postings if p.company}),
            "top_skills": dict(skill_dist.most_common(20)),
            "top_locations": dict(loc_dist.most_common(15)),
            "remote_distribution": dict(remote_dist),
            "fde_score_stats": {
                "mean": round(
                    sum(p.fde_score for p in self.postings) / max(len(self.postings), 1),
                    3,
                ),
                "above_threshold": sum(
                    1 for p in self.postings if p.fde_score >= 0.5
                ),
            },
            "trends": [
                {"period": t.period, "count": t.count}
                for t in self.trends_by_month()
            ],
        }
