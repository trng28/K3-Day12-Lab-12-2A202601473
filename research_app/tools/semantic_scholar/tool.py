from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any

import httpx

from tools._shared import TIMEOUT, err
from tools.papers.tool import Paper, _run_async


SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
MIN_INTERVAL_SECONDS = 1.0
FIELDS = ",".join(
    [
        "paperId", "title", "abstract", "authors", "publicationDate", "year",
        "url", "openAccessPdf", "fieldsOfStudy", "externalIds",
    ]
)
_last_request_at = 0.0
_rate_limit_lock = threading.Lock()


def semantic_scholar_api_key() -> str | None:
    return (
        os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        or os.getenv("SEMANTIC_SCHOLAR_API")
        or os.getenv("SEMATIC_SCHOLAR_API")
    )


async def _respect_rate_limit() -> None:
    global _last_request_at
    with _rate_limit_lock:
        elapsed = time.monotonic() - _last_request_at
        delay = max(0.0, MIN_INTERVAL_SECONDS - elapsed)
        _last_request_at = time.monotonic() + delay
    if delay:
        await asyncio.sleep(delay)


def _paper_from_api(item: dict[str, Any]) -> Paper:
    semantic_id = str(item.get("paperId") or "")
    published = item.get("publicationDate")
    if not published and item.get("year"):
        published = f"{item['year']}-01-01"
    published = published or ""
    pdf = item.get("openAccessPdf") or {}
    arxiv_id = (item.get("externalIds") or {}).get("ArXiv")
    stable_id = f"arxiv:{arxiv_id}" if arxiv_id else f"semantic_scholar:{semantic_id}"
    source_url = item.get("url") or f"https://www.semanticscholar.org/paper/{semantic_id}"
    return Paper(
        paper_id=stable_id,
        title=" ".join((item.get("title") or "Untitled paper").split()),
        abstract=" ".join((item.get("abstract") or "").split()),
        authors=[
            author["name"] for author in (item.get("authors") or [])
            if author.get("name")
        ],
        published_at=published,
        updated_at=published,
        pdf_url=pdf.get("url"),
        source_url=source_url,
        categories=item.get("fieldsOfStudy") or [],
    )


async def search_semantic_scholar(
    query: str,
    max_results: int = 10,
    *,
    client: httpx.AsyncClient | None = None,
) -> list[Paper]:
    max_results = min(max(int(max_results), 1), 100)
    api_key = semantic_scholar_api_key()
    headers = {"x-api-key": api_key} if api_key else {}
    params = {
        "query": " ".join(query.split()).replace("-", " "),
        "limit": max_results,
        "fields": FIELDS,
    }
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=TIMEOUT, headers=headers)
    try:
        response: httpx.Response | None = None
        for attempt in range(3):
            await _respect_rate_limit()
            response = await client.get(SEARCH_URL, params=params, headers=headers)
            if response.status_code != 429:
                break
            retry_after = response.headers.get("retry-after")
            await asyncio.sleep(float(retry_after) if retry_after else 2 * (attempt + 1))
        assert response is not None
        if response.status_code == 429 and not api_key:
            raise RuntimeError(
                "Semantic Scholar public quota returned HTTP 429. Configure "
                "SEMANTIC_SCHOLAR_API_KEY in .env for a dedicated rate limit."
            )
        response.raise_for_status()
        return [_paper_from_api(item) for item in response.json().get("data", [])]
    finally:
        if owns_client:
            await client.aclose()


def semantic_scholar_search(query: str = "", max_results: int = 5) -> dict[str, Any]:
    try:
        papers = _run_async(search_semantic_scholar(query, max_results))
        items = [
            {
                "paper_id": paper.paper_id,
                "title": paper.title,
                "summary": paper.abstract,
                "abstract": paper.abstract,
                "authors": paper.authors,
                "published_at": paper.published_at,
                "updated_at": paper.updated_at,
                "url": paper.source_url,
                "source_url": paper.source_url,
                "pdf_url": paper.pdf_url,
                "source": "semanticscholar.org",
                "categories": paper.categories,
            }
            for paper in papers
        ]
        return {
            "tool": "semantic_scholar_search",
            "query": query,
            "items": items,
            "total_results": len(items),
            "authenticated": bool(semantic_scholar_api_key()),
            "rate_limit_note": "Authenticated requests are spaced by at least 1 second.",
        }
    except Exception as exc:
        return err("semantic_scholar_search", exc)
