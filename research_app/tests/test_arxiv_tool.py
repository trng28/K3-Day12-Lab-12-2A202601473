from __future__ import annotations

import asyncio

import httpx

import tools.papers.tool as arxiv_tool


ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/2003.00744v2</id>
    <updated>2020-03-10T00:00:00Z</updated>
    <published>2020-03-02T00:00:00Z</published>
    <title>PhoBERT: Pre-trained language models for Vietnamese</title>
    <summary>A Vietnamese language model.</summary>
    <author><name>Dat Quoc Nguyen</name></author>
    <link href="https://arxiv.org/pdf/2003.00744v2" type="application/pdf"/>
    <category term="cs.CL"/>
  </entry>
</feed>"""


def test_search_arxiv_parses_atom(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert " AND " in request.url.params["search_query"]
        return httpx.Response(200, request=request, text=ATOM)

    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(arxiv_tool.httpx, "AsyncClient", client_factory)
    papers = asyncio.run(
        arxiv_tool.search_arxiv("Vietnamese pretrained language models", 2)
    )

    assert papers[0].paper_id == "arxiv:2003.00744v2"
    assert papers[0].title.startswith("PhoBERT")
