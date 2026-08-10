from __future__ import annotations

import asyncio

from research_workflow import ResearchWorkflow
from providers.base import ModelResponse
from tools.papers.tool import Paper


def paper(paper_id: str, title: str, abstract: str) -> Paper:
    return Paper(
        paper_id=paper_id,
        title=title,
        abstract=abstract,
        authors=["Researcher"],
        published_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        source_url=f"https://arxiv.org/abs/{paper_id.split(':')[-1]}",
    )


def test_workflow_deduplicates_ranks_and_publishes() -> None:
    papers = [
        paper(
            "arxiv:1",
            "Hybrid retrieval for Vietnamese legal question answering",
            "We evaluate Recall@10 on the VLegal benchmark.",
        ),
        paper(
            "arxiv:2",
            "Dense retrieval and reranking",
            "We report Recall@10 on another corpus.",
        ),
    ]

    async def fake_search(query: str, max_results: int) -> list[Paper]:
        return papers

    workflow = ResearchWorkflow({"fake": fake_search})
    result = asyncio.run(
        workflow.run("Vietnamese legal retrieval and answer generation")
    )

    assert len(result.evidence) == 2
    assert result.evidence[0].role == "core"
    assert "Synthesis" in result.report
    assert "Do not directly compare recall@10" in result.report


def test_empty_search_still_produces_actionable_report() -> None:
    async def empty_search(query: str, max_results: int) -> list[Paper]:
        return []

    result = asyncio.run(ResearchWorkflow({"empty": empty_search}).run("legal RAG"))

    assert result.evidence == []
    assert "Insufficient evidence" in result.report
    assert "will not generate a synthetic conclusion" in result.report
    assert "No sources selected" not in result.report


def test_general_nlp_question_does_not_force_legal_workstreams() -> None:
    async def failing_search(query: str, max_results: int) -> list[Paper]:
        raise ConnectionError("source unavailable")

    workflow = ResearchWorkflow({"failing": failing_search})
    result = asyncio.run(workflow.run("What are current Vietnamese pretrained models?"))

    assert "Vietnamese legal datasets" not in result.plan.workstreams
    assert "pretrained language models" in result.plan.workstreams
    assert result.source_errors
    assert "ConnectionError" in result.report
    assert "model inventory" not in result.report
    assert "Insufficient evidence" in result.report


def test_free_arxiv_fallback_skips_unkeyed_semantic_scholar(monkeypatch) -> None:
    for name in (
        "SEMANTIC_SCHOLAR_API_KEY",
        "SEMANTIC_SCHOLAR_API",
        "SEMATIC_SCHOLAR_API",
    ):
        monkeypatch.delenv(name, raising=False)
    semantic_calls = 0

    async def arxiv_search(query: str, max_results: int) -> list[Paper]:
        assert query.startswith("Vietnamese natural language processing")
        return [
            paper("arxiv:free", "Vietnamese NLP benchmark", "A free benchmark.")
        ]

    async def semantic_search(query: str, max_results: int) -> list[Paper]:
        nonlocal semantic_calls
        semantic_calls += 1
        return []

    workflow = ResearchWorkflow(
        {"arxiv": arxiv_search, "semantic_scholar": semantic_search}
    )
    result = asyncio.run(
        workflow.run(
            "I want to research about Vietnamese NLP, give me papers about datasets"
        )
    )

    assert semantic_calls == 0
    assert result.evidence
    assert "arxiv: 4 papers retrieved" in result.report
    assert "free arXiv search remains active" in result.report


def test_llm_synthesis_requires_and_preserves_citations() -> None:
    source = paper(
        "arxiv:cited",
        "A Vietnamese Multimodal Dataset",
        "We introduce an image-text benchmark for Vietnamese.",
    )

    async def fake_search(query: str, max_results: int) -> list[Paper]:
        return [source]

    class FakeProvider:
        def complete(self, messages, tools, **kwargs):
            assert "A Vietnamese Multimodal Dataset" in messages[1]["content"]
            return ModelResponse(
                text=(
                    "## Dataset landscape\n\n"
                    "The evidence describes a Vietnamese image-text benchmark [P1].\n\n"
                    "## Research gap\n\nDataset scale is not identified [P1]."
                )
            )

    workflow = ResearchWorkflow(
        {"fake": fake_search},
        llm_provider=FakeProvider(),
        use_llm=True,
    )
    result = asyncio.run(workflow.run("Analyze Vietnamese multimodal datasets"))

    assert "# Research analysis" in result.report
    assert "[P1]" in result.report
    assert "Verified references" in result.report
    assert source.source_url in result.report


def test_multimodal_planner_and_relevance_gate_reject_unrelated_papers() -> None:
    workflow = ResearchWorkflow({"fake": lambda query, limit: None})
    workflow.enforce_anchor_relevance = True
    plan = workflow.plan("Analyze datasets for Vietnamese multimodal research")
    unrelated = paper(
        "arxiv:cricket",
        "Cricket Shot Detection",
        "A video classification system for sports analytics.",
    )
    relevant = paper(
        "arxiv:vi-mm",
        "A Vietnamese Multimodal Dataset",
        "An image-text dataset and benchmark for Vietnamese.",
    )

    ranked = workflow.rank(
        plan,
        [("image text datasets", unrelated), ("image text datasets", relevant)],
    )

    assert plan.search_topic == "Vietnamese multimodal datasets"
    assert plan.workstreams == [
        "image text datasets",
        "visual question answering datasets",
        "speech text multimodal datasets",
        "multimodal benchmarks and evaluation",
    ]
    assert [item.paper.paper_id for item in ranked] == ["arxiv:vi-mm"]
