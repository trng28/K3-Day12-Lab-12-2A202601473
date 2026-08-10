from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from typing import Any, Literal
from urllib.parse import urlencode

import feedparser
import httpx
from pydantic import BaseModel, Field

from tools._shared import TIMEOUT, err


ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_MIN_INTERVAL_SECONDS = 3.0
_last_arxiv_request_at = 0.0
_rate_limit_lock = threading.Lock()


class Paper(BaseModel):
    paper_id: str
    title: str
    abstract: str
    authors: list[str]
    published_at: str
    updated_at: str
    pdf_url: str | None = None
    source_url: str
    categories: list[str] = Field(default_factory=list)


def _arxiv_user_agent() -> str:
    return os.getenv(
        "ARXIV_USER_AGENT",
        "AI20k-Day04-Research-Agent/1.0 (educational lab; contact: local)",
    )


def _arxiv_search_query(query: str) -> str:
    cleaned = " ".join((query or "").split())
    if ":" in cleaned:
        return cleaned
    query_stopwords = {
        "about", "any", "are", "can", "current", "give", "help", "me", "please",
        "problem", "some", "the", "what", "which", "with", "các", "cho", "có",
        "hiện", "một", "những", "nào", "trên",
    }
    terms = [
        term for term in re.findall(r"[\w\-]+", cleaned, flags=re.UNICODE)
        if len(term) > 1 and term.casefold() not in query_stopwords
    ]
    # Remove conversational filler first, then require the remaining topic terms.
    # This avoids both zero-result queries caused by "give me..." and noisy OR results.
    return " AND ".join(f"all:{term}" for term in terms[:8]) or cleaned


async def _respect_arxiv_rate_limit() -> None:
    global _last_arxiv_request_at
    with _rate_limit_lock:
        elapsed = time.monotonic() - _last_arxiv_request_at
        delay = max(0.0, ARXIV_MIN_INTERVAL_SECONDS - elapsed)
        _last_arxiv_request_at = time.monotonic() + delay
    if delay:
        await asyncio.sleep(delay)


async def search_arxiv(
    query: str,
    max_results: int = 10,
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = "relevance",
) -> list[Paper]:
    """Search arXiv and return a provider-independent paper model."""
    max_results = min(max(int(max_results), 1), 25)
    parameters = {
        "search_query": _arxiv_search_query(query),
        "start": 0,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": "descending",
    }
    url = f"{ARXIV_API_URL}?{urlencode(parameters)}"

    response: httpx.Response | None = None
    async with httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": _arxiv_user_agent()},
    ) as client:
        for attempt in range(3):
            await _respect_arxiv_rate_limit()
            response = await client.get(url)
            if response.status_code != 429:
                break
            await asyncio.sleep(3 * (attempt + 1))

    assert response is not None
    response.raise_for_status()
    feed = feedparser.parse(response.text)
    if getattr(feed, "bozo", False) and not feed.entries:
        raise ValueError(f"Invalid arXiv Atom response: {feed.bozo_exception}")

    papers: list[Paper] = []
    for entry in feed.entries:
        arxiv_id = entry.id.rsplit("/", 1)[-1]
        pdf_url = next(
            (
                link.href
                for link in entry.get("links", [])
                if link.get("type") == "application/pdf"
            ),
            None,
        )
        papers.append(
            Paper(
                paper_id=f"arxiv:{arxiv_id}",
                title=" ".join(entry.title.split()),
                abstract=" ".join(entry.summary.split()),
                authors=[author.name for author in entry.get("authors", [])],
                published_at=entry.published,
                updated_at=entry.updated,
                pdf_url=pdf_url,
                source_url=entry.id,
                categories=[tag.term for tag in entry.get("tags", [])],
            )
        )
    return papers


def _run_async(coro: Any) -> Any:
    """Run an async tool from both normal code and an already-running event loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: list[Any] = []
    failure: list[BaseException] = []

    def runner() -> None:
        try:
            result.append(asyncio.run(coro))
        except BaseException as exc:
            failure.append(exc)

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if failure:
        raise failure[0]
    return result[0]


def arxiv_search(query: str = "", max_results: int = 5, sort_by: str = "relevance") -> dict[str, Any]:
    """Compatibility wrapper for the existing synchronous tool registry."""
    try:
        normalized_sort = (
            sort_by
            if sort_by in {"relevance", "lastUpdatedDate", "submittedDate"}
            else "relevance"
        )
        papers = _run_async(search_arxiv(query, max_results, normalized_sort))
        items = [
            {
                "arxiv_id": paper.paper_id.removeprefix("arxiv:"),
                "paper_id": paper.paper_id,
                "title": paper.title,
                "summary": paper.abstract,
                "abstract": paper.abstract,
                "authors": paper.authors,
                "published": paper.published_at,
                "published_at": paper.published_at,
                "updated": paper.updated_at,
                "updated_at": paper.updated_at,
                "url": paper.source_url,
                "source_url": paper.source_url,
                "pdf_url": paper.pdf_url,
                "source": "arxiv.org",
                "primary_category": paper.categories[0] if paper.categories else None,
                "categories": paper.categories,
            }
            for paper in papers
        ]
        return {
            "tool": "arxiv_search",
            "query": query,
            "items": items,
            "total_results": len(items),
            "rate_limit_note": "Requests are spaced by at least 3 seconds in-process.",
        }
    except Exception as exc:
        return err("arxiv_search", exc)
