from __future__ import annotations

import asyncio

import httpx

from tools.semantic_scholar.tool import search_semantic_scholar


def test_semantic_scholar_maps_api_response(monkeypatch) -> None:
    monkeypatch.setenv("SEMATIC_SCHOLAR_API", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "test-key"
        assert request.url.params["query"] == "legal retrieval"
        return httpx.Response(
            200,
            request=request,
            json={
                "data": [{
                    "paperId": "s2-id",
                    "title": " A Legal Retrieval Paper ",
                    "abstract": "Hybrid retrieval.",
                    "authors": [{"name": "Ada"}],
                    "publicationDate": "2025-05-01",
                    "url": "https://www.semanticscholar.org/paper/s2-id",
                    "openAccessPdf": {"url": "https://example.org/paper.pdf"},
                    "fieldsOfStudy": ["Computer Science"],
                    "externalIds": {"ArXiv": "2505.00001"},
                }]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await search_semantic_scholar("legal-retrieval", 5, client=client)

    papers = asyncio.run(run())
    assert papers[0].paper_id == "arxiv:2505.00001"
    assert papers[0].authors == ["Ada"]
    assert papers[0].pdf_url == "https://example.org/paper.pdf"
