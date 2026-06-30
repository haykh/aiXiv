import httpx
from datetime import datetime, timezone
import re

import feedparser
from sqlmodel import Session, select

from aiXiv import __version__
from aiXiv.database.tables import Paper
from aiXiv.arxiv.categories import ArxivCategoryValue


arxiv_api_url = "https://export.arxiv.org/api/query"


def _parse_feed(text: str) -> tuple[list[Paper], int]:
    parsed = feedparser.parse(text)
    papers: list[Paper] = []
    for p in parsed.entries:
        papers.append(
            Paper(
                arxiv_id=re.sub(r"v\d+$", "", p.id.split("/abs/")[-1]),
                title=p.title,
                abstract=p.summary,
                authors=[a.name for a in p.authors],
                categories=[t["term"] for t in p.tags],
                published_at=datetime.strptime(
                    p.published, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc),
                url=p.link,
            )
        )
    # arXiv reports the total number of matches via OpenSearch — used for paging
    total = int(parsed.feed.get("opensearch_totalresults", len(papers)))
    return papers, total


async def fetch_from_arxiv(
    category: ArxivCategoryValue,
    page: int,
    start: datetime,
    end: datetime,
    max_results: int,
) -> tuple[list[Paper], int]:
    params = {
        "search_query": f"cat:{category.value} AND submittedDate:[{start.strftime('%Y%m%d%H%M')} TO {end.strftime('%Y%m%d%H%M')}]",
        "start": (page - 1) * max_results,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            arxiv_api_url,
            params=params,
            headers={"User-Agent": f"aiXiv/{__version__}"},
        )
        resp.raise_for_status()
        return _parse_feed(resp.text)


async def fetch_from_arxiv_by_ids(arxiv_ids: list[str]) -> list[Paper]:
    params = {"id_list": ",".join(arxiv_ids), "max_results": len(arxiv_ids)}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            arxiv_api_url,
            params=params,
            headers={"User-Agent": f"aiXiv/{__version__}"},
        )
        resp.raise_for_status()
        papers, _ = _parse_feed(resp.text)
        return papers


def store_papers(papers: list[Paper], session: Session) -> int:
    new_papers_committed = 0
    for paper in papers:
        existing = session.exec(
            select(Paper).where(Paper.arxiv_id == paper.arxiv_id)
        ).first()
        if existing is None:
            session.add(paper)
            new_papers_committed += 1
    session.commit()
    return new_papers_committed
