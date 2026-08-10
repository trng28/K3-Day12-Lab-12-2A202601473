from __future__ import annotations

import asyncio
from pathlib import Path

from research_chat import ResearchChatbot
from research_workflow import ResearchWorkflow
from tools.papers.tool import Paper


def test_chat_research_followups_and_save(tmp_path: Path) -> None:
    async def fake_search(query: str, max_results: int) -> list[Paper]:
        return [
            Paper(
                paper_id="arxiv:1234.5678",
                title="Hybrid retrieval for Vietnamese law",
                abstract="Recall@10 is evaluated on VLegal.",
                authors=["A. Researcher"],
                published_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                source_url="https://arxiv.org/abs/1234.5678",
            )
        ]

    chatbot = ResearchChatbot(ResearchWorkflow({"fake": fake_search}))
    response = asyncio.run(chatbot.respond("Vietnamese legal retrieval"))

    assert "Research complete" in response
    assert "Hybrid retrieval for Vietnamese law" in asyncio.run(
        chatbot.respond("/sources")
    )
    natural_sources = asyncio.run(chatbot.respond("give me source citation"))
    assert "A. Researcher (2026)" in natural_sources
    assert "https://arxiv.org/abs/1234.5678" in natural_sources
    assert chatbot.will_search("give me source citation") is False
    assert chatbot.will_search("Vietnamese multimodal datasets") is True
    output = tmp_path / "report.md"
    assert "Saved:" in asyncio.run(chatbot.respond(f'/save "{output}"'))
    assert output.exists()


def test_source_request_without_previous_research_is_not_misrouted() -> None:
    chatbot = ResearchChatbot()
    response = asyncio.run(chatbot.respond("/sources"))
    assert response == "No research result yet. Ask a question first."


def test_research_response_streams_workflow_stages() -> None:
    async def fake_search(query: str, max_results: int) -> list[Paper]:
        return []

    chatbot = ResearchChatbot(ResearchWorkflow({"fake": fake_search}))

    async def collect() -> list[str]:
        return [
            chunk
            async for chunk in chatbot.respond_stream("Vietnamese NLP challenges")
        ]

    chunks = asyncio.run(collect())
    combined = "".join(chunks)
    assert len(chunks) > 8
    assert "[Planner]" in combined
    assert "[Search]" in combined
    assert "[Ranking]" in combined
    assert "[Reader]" in combined
    assert "[Critic]" in combined
    assert "[Publisher]" in combined
    assert "# Insufficient evidence" in combined
    assert "refusing unsupported synthesis" in combined
