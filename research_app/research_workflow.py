from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

from env_loader import load_lab_env
from providers import make_provider
from tools._shared import terms
from tools.papers.tool import Paper, search_arxiv
from tools.semantic_scholar.tool import (
    search_semantic_scholar,
    semantic_scholar_api_key,
)


SearchAdapter = Callable[[str, int], Awaitable[list[Paper]]]


DEFAULT_WORKSTREAMS = [
    "Vietnamese legal datasets",
    "dense retrievers",
    "hybrid retrieval",
    "reranking",
    "legal answer generation",
    "evaluation metrics",
]

GENERAL_NLP_WORKSTREAMS = [
    "pretrained language models",
    "datasets and benchmarks",
    "Vietnamese NLP tasks",
    "evaluation and open challenges",
]

MULTIMODAL_WORKSTREAMS = [
    "image text datasets",
    "visual question answering datasets",
    "speech text multimodal datasets",
    "multimodal benchmarks and evaluation",
]


@dataclass
class ResearchPlan:
    question: str
    workstreams: list[str]
    search_topic: str = ""
    searches_per_stream: int = 8
    candidate_limit: int = 20
    core_limit: int = 8
    supporting_limit: int = 4


@dataclass
class Evidence:
    paper: Paper
    workstream: str
    relevance_score: float
    role: str = "candidate"
    dataset: str | None = None
    method: str | None = None
    metrics: list[str] = field(default_factory=list)
    limitation: str | None = None


@dataclass
class Critique:
    warnings: list[str] = field(default_factory=list)
    comparison_rules: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    plan: ResearchPlan
    evidence: list[Evidence]
    critique: Critique
    report: str
    source_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "plan": asdict(self.plan),
            "evidence": [
                {**asdict(item), "paper": item.paper.model_dump()}
                for item in self.evidence
            ],
            "critique": asdict(self.critique),
            "source_errors": self.source_errors,
            "report": self.report,
        }


class ResearchWorkflow:
    """A transparent planner → search → rank → read → critique → publish pipeline."""

    def __init__(
        self,
        search_adapters: dict[str, SearchAdapter] | None = None,
        *,
        llm_provider: object | None = None,
        use_llm: bool | None = None,
    ) -> None:
        custom_search_adapters = search_adapters is not None
        self.search_adapters = search_adapters or {
            "arxiv": search_arxiv,
            "semantic_scholar": search_semantic_scholar,
        }
        self.last_search_errors: list[str] = []
        self.last_source_notes: list[str] = []
        self.last_source_counts: dict[str, int] = {}
        self.last_synthesis_note: str | None = None
        self.current_plan: ResearchPlan | None = None
        self.llm_provider = llm_provider
        self.enforce_anchor_relevance = not custom_search_adapters
        self.use_llm = (
            not custom_search_adapters
            if use_llm is None
            else use_llm
        )

    @staticmethod
    def _search_topic(question: str) -> str:
        normalized = question.casefold()
        if "vietnam" in normalized and any(
            marker in normalized for marker in ("multimodal", "multi-modal")
        ):
            return "Vietnamese multimodal datasets"
        if "vietnam" in normalized and any(
            marker in normalized for marker in ("nlp", "natural language", "ngôn ngữ")
        ):
            return "Vietnamese natural language processing"
        if "vietnam" in normalized and any(
            marker in normalized for marker in ("legal", "law", "luật", "pháp")
        ):
            return "Vietnamese legal NLP"
        cleaned = re.sub(
            r"\b(?:i want to|research about|give me|show me|find|papers? about|"
            r"some|please|tôi muốn|cho tôi|tìm|nghiên cứu về)\b",
            " ",
            question,
            flags=re.IGNORECASE,
        )
        return " ".join(cleaned.replace(",", " ").replace("?", " ").split())[:180]

    def plan(self, question: str) -> ResearchPlan:
        normalized = question.casefold()
        legal_markers = ("legal", "law", "luật", "pháp lý", "pháp luật")
        if any(marker in normalized for marker in legal_markers):
            workstreams = DEFAULT_WORKSTREAMS
        elif any(marker in normalized for marker in ("multimodal", "multi-modal")):
            workstreams = MULTIMODAL_WORKSTREAMS
        else:
            workstreams = GENERAL_NLP_WORKSTREAMS
        plan = ResearchPlan(
            question=question,
            workstreams=list(workstreams),
            search_topic=self._search_topic(question),
        )
        self.current_plan = plan
        return plan

    async def search(self, plan: ResearchPlan) -> list[tuple[str, Paper]]:
        self.last_search_errors = []
        self.last_source_notes = []
        self.last_source_counts = {source: 0 for source in self.search_adapters}
        tasks: list[tuple[str, str, Awaitable[list[Paper]]]] = []
        for source, adapter in self.search_adapters.items():
            if source == "semantic_scholar" and not semantic_scholar_api_key():
                self.last_source_notes.append(
                    "semantic_scholar: skipped because no API key is configured; "
                    "free arXiv search remains active."
                )
                continue
            source_workstreams = (
                ["broad literature search"]
                if source == "semantic_scholar"
                else plan.workstreams
            )
            for workstream in source_workstreams:
                query = f"{plan.search_topic} {workstream}"
                tasks.append(
                    (source, workstream, adapter(query, plan.searches_per_stream))
                )
        results = await asyncio.gather(
            *(task for _, _, task in tasks), return_exceptions=True
        )
        found: list[tuple[str, Paper]] = []
        for (source, workstream, _), result in zip(tasks, results):
            if isinstance(result, BaseException):
                if type(result).__name__ == "HTTPStatusError":
                    response = getattr(result, "response", None)
                    status = getattr(response, "status_code", "unknown")
                    message = f"HTTP {status}; the source rate limit or request failed"
                else:
                    message = str(result).strip() or type(result).__name__
                self.last_search_errors.append(
                    f"{source} ({workstream}): {type(result).__name__}: {message}"
                )
                continue
            self.last_source_counts[source] += len(result)
            found.extend((workstream, paper) for paper in result)
        return found

    def rank(
        self, plan: ResearchPlan, papers: Sequence[tuple[str, Paper]]
    ) -> list[Evidence]:
        query_terms = terms(f"{plan.question} {' '.join(plan.workstreams)}")
        anchor_terms = terms(plan.search_topic)
        minimum_anchor_overlap = 1 if len(anchor_terms) <= 2 else 2
        deduplicated: dict[str, Evidence] = {}
        for workstream, paper in papers:
            document_terms = terms(f"{paper.title} {paper.abstract}")
            anchor_overlap = len(anchor_terms & document_terms)
            if (
                self.enforce_anchor_relevance
                and anchor_overlap < minimum_anchor_overlap
            ):
                continue
            overlap = len(query_terms & document_terms)
            coverage = overlap / max(1, len(query_terms))
            title_overlap = len(query_terms & terms(paper.title))
            score = round(
                coverage + title_overlap * 0.08 + anchor_overlap * 0.12,
                4,
            )
            item = Evidence(paper=paper, workstream=workstream, relevance_score=score)
            previous = deduplicated.get(paper.paper_id)
            if previous is None or item.relevance_score > previous.relevance_score:
                deduplicated[paper.paper_id] = item

        ranked = sorted(
            deduplicated.values(),
            key=lambda item: (item.relevance_score, item.paper.published_at),
            reverse=True,
        )[: plan.candidate_limit]
        for index, item in enumerate(ranked):
            if index < plan.core_limit:
                item.role = "core"
            elif index < plan.core_limit + plan.supporting_limit:
                item.role = "supporting"
        return ranked

    def read(self, evidence: list[Evidence]) -> None:
        """Extract conservative metadata hints; full-text/LLM readers can replace this."""
        metric_pattern = re.compile(
            r"\b(?:Recall|Precision|MRR|MAP|NDCG|F1|EM)(?:@\d+)?\b",
            re.IGNORECASE,
        )
        dataset_pattern = re.compile(
            r"(?:on|using|dataset|corpus|benchmark)\s+(?:the\s+)?([A-Z][A-Za-z0-9_-]{2,})"
        )
        for item in evidence:
            text = f"{item.paper.title}. {item.paper.abstract}"
            item.metrics = sorted(set(metric_pattern.findall(text)), key=str.lower)
            dataset_match = dataset_pattern.search(text)
            item.dataset = dataset_match.group(1) if dataset_match else None
            item.method = item.workstream
            if re.search(r"\b(?:limitation|limited|however|future work)\b", text, re.I):
                item.limitation = "The abstract signals a limitation; verify it in full text."

    def critique(self, evidence: Sequence[Evidence]) -> Critique:
        critique = Critique(
            comparison_rules=[
                "Compare metric values only when dataset, split, retrieval depth, and evaluation protocol match.",
                "Treat abstract-only extraction as provisional until verified against the paper tables.",
            ]
        )
        metric_contexts: dict[str, set[str]] = {}
        for item in evidence:
            context = item.dataset or "dataset not identified"
            for metric in item.metrics:
                metric_contexts.setdefault(metric.lower(), set()).add(context)
        for metric, contexts in metric_contexts.items():
            if len(contexts) > 1 or "dataset not identified" in contexts:
                critique.warnings.append(
                    f"Do not directly compare {metric}: reported contexts are "
                    f"{', '.join(sorted(contexts))}."
                )
        critique_context = " ".join(item.workstream for item in evidence)
        if self.current_plan:
            critique_context = f"{self.current_plan.question} {critique_context}"
        question_is_legal = any(
            marker in critique_context.casefold()
            for marker in ("legal", "law", "luật")
        )
        if question_is_legal and not any(
            "vietnam" in (item.dataset or "").lower() for item in evidence
        ):
            critique.warnings.append(
                "No clearly identified Vietnamese legal benchmark was found in metadata; "
                "treat this as a gap to verify with full-text reading and broader sources."
            )
        return critique

    def publish(
        self, plan: ResearchPlan, evidence: Sequence[Evidence], critique: Critique
    ) -> str:
        core = [item for item in evidence if item.role == "core"]
        supporting = [item for item in evidence if item.role == "supporting"]
        normalized_question = plan.question.casefold()

        def references(items: Sequence[Evidence]) -> str:
            if not items:
                return "- No sources selected."
            return "\n".join(
                f"- [{item.paper.title}]({item.paper.source_url}) — "
                f"{item.workstream}; score {item.relevance_score:.3f}"
                for item in items
            )

        warnings = "\n".join(f"- {warning}" for warning in critique.warnings)
        source_failures = "\n".join(f"- {error}" for error in self.last_search_errors)
        source_counts = "\n".join(
            f"- {source}: {count} papers retrieved."
            for source, count in self.last_source_counts.items()
            if count
        )
        source_notes = "\n".join(f"- {note}" for note in self.last_source_notes)
        source_status = "\n".join(
            part for part in (source_counts, source_notes, source_failures) if part
        )
        if any(marker in normalized_question for marker in ("legal", "law", "luật", "pháp")):
            synthesis = (
                "Evaluate sparse, dense, and hybrid retrieval before answer generation. "
                "Use versioned legal sources, passage-level citations, and a Vietnamese "
                "legal benchmark with explicit relevance judgments."
            )
            backlog = """1. Define Vietnamese legal queries, relevance judgments, document versions, and splits.
2. Establish BM25 and multilingual dense-retrieval baselines.
3. Evaluate reciprocal-rank fusion and learned hybrid weighting.
4. Add a multilingual cross-encoder reranker and measure latency/quality trade-offs.
5. Evaluate retrieval separately from grounded answer correctness and citation fidelity."""
        elif any(marker in normalized_question for marker in ("model", "pretrain", "language model")):
            synthesis = (
                "Use the selected core papers to build a model inventory containing model "
                "family, tokenizer, pretraining corpus, parameter count, license, supported "
                "tasks, and benchmark results. Do not infer model quality from paper titles."
            )
            backlog = """1. Create a versioned catalog of Vietnamese-only and multilingual pretrained models.
2. Record tokenizer coverage, training-data provenance, license, and context length.
3. Re-evaluate models on the same Vietnamese datasets and data splits.
4. Test dialects, code-switching, domain shift, safety, and inference cost."""
        else:
            synthesis = (
                "Organize Vietnamese NLP problems by task, dataset availability, evaluation "
                "quality, domain coverage, and deployment constraints. Prioritize gaps that "
                "have reproducible datasets and measurable user impact."
            )
            backlog = """1. Audit datasets for dialect, domain, demographic, and temporal coverage.
2. Benchmark tokenization, normalization, segmentation, and code-switching robustness.
3. Evaluate information extraction, retrieval, generation, and factuality separately.
4. Study low-resource domains, noisy user text, speech-text interaction, and safety.
5. Publish reproducible splits, licenses, baselines, and error analyses."""
        return f"""# Research report: {plan.question}

Search topic: `{plan.search_topic}`

## Synthesis

{synthesis}

## Core papers

{references(core)}

## Supporting sources

{references(supporting)}

## Critic notes

{warnings or "- No metadata-level comparison warning was triggered."}

## Source status

{source_status or "- All configured search calls completed successfully."}

## Experiment backlog

{backlog}
"""

    def publish_no_evidence(self, plan: ResearchPlan) -> str:
        source_failures = "\n".join(
            f"- {error}" for error in self.last_search_errors
        )
        source_notes = "\n".join(f"- {note}" for note in self.last_source_notes)
        status = "\n".join(
            part for part in (source_notes, source_failures) if part
        )
        return f"""# Insufficient evidence: {plan.question}

The agent could not produce an evidence-grounded analysis because no relevant
papers were retrieved. It will not generate a synthetic conclusion without
sources.

## Source status

{status or "- The configured sources returned no matching papers."}

## Recommended next actions

1. Shorten or broaden the research topic.
2. Try related academic terminology or remove overly narrow constraints.
3. Verify the Semantic Scholar API key if that source is rate-limited.
4. Retry later or use the free arXiv search as the primary source.
"""

    def _canonical_references(self, evidence: Sequence[Evidence]) -> str:
        selected = [
            item for item in evidence if item.role in {"core", "supporting"}
        ]
        return "\n".join(
            f"- [P{index}] [{item.paper.title}]({item.paper.source_url})"
            for index, item in enumerate(selected, start=1)
        )

    async def synthesize(
        self,
        plan: ResearchPlan,
        evidence: Sequence[Evidence],
        critique: Critique,
    ) -> str:
        self.last_synthesis_note = None
        if not evidence:
            return self.publish_no_evidence(plan)
        if not self.use_llm:
            self.last_synthesis_note = "LLM synthesis disabled; deterministic fallback used."
            return self.publish(plan, evidence, critique)

        selected = [
            item for item in evidence if item.role in {"core", "supporting"}
        ]
        evidence_blocks: list[str] = []
        for index, item in enumerate(selected, start=1):
            paper = item.paper
            evidence_blocks.append(
                "\n".join(
                    [
                        f"[P{index}] {paper.title}",
                        f"URL: {paper.source_url}",
                        f"Authors: {', '.join(paper.authors)}",
                        f"Published: {paper.published_at}",
                        f"Workstream: {item.workstream}",
                        f"Abstract: {paper.abstract[:1400]}",
                        f"Extracted metrics: {', '.join(item.metrics) or 'not identified'}",
                        f"Extracted dataset: {item.dataset or 'not identified'}",
                    ]
                )
            )
        critic_rules = "\n".join(
            f"- {rule}" for rule in [*critique.comparison_rules, *critique.warnings]
        )
        system_prompt = """You are an academic research synthesizer.
Write an analytical Markdown answer grounded only in the supplied papers.
Adapt the report structure to the user's intent; do not reuse a fixed template.
Every factual claim about a paper, dataset, method, metric, or limitation must
end with one or more citations in the exact form [P1], [P2], etc.
Do not invent papers, numerical results, datasets, or capabilities.
If evidence is incomplete, state the limitation explicitly.
Do not directly compare metrics unless dataset and evaluation protocol match.
Answer in the same language as the user's question."""
        user_prompt = f"""Research question:
{plan.question}

Evidence:
{chr(10).join(evidence_blocks)}

Critic constraints:
{critic_rules}

Produce a useful analysis with an executive summary, intent-specific comparison,
research gaps, and actionable next steps. Cite all evidence-backed claims."""
        try:
            provider = self.llm_provider or make_provider(
                os.getenv("LLM_PROVIDER", "openai")
            )
            response = await asyncio.to_thread(
                provider.complete,
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                [],
                model=os.getenv("LLM_MODEL") or None,
                temperature=0.2,
            )
            draft = (response.text or "").strip()
            cited_ids = {
                int(value) for value in re.findall(r"\[P(\d+)\]", draft)
            }
            if not draft or not cited_ids or any(
                value < 1 or value > len(selected) for value in cited_ids
            ):
                raise ValueError("LLM response did not contain valid evidence citations")
            return (
                f"# Research analysis: {plan.question}\n\n"
                f"{draft}\n\n## Verified references\n\n"
                f"{self._canonical_references(evidence)}\n"
            )
        except Exception as exc:
            self.last_synthesis_note = (
                f"LLM synthesis unavailable ({type(exc).__name__}); "
                "deterministic fallback used."
            )
            fallback = self.publish(plan, evidence, critique)
            return (
                f"> **Synthesis notice:** {self.last_synthesis_note}\n\n{fallback}"
            )

    async def run(self, question: str) -> WorkflowResult:
        plan = self.plan(question)
        found = await self.search(plan)
        evidence = self.rank(plan, found)
        self.read(evidence)
        critique = self.critique(evidence)
        report = await self.synthesize(plan, evidence, critique)
        return WorkflowResult(
            plan, evidence, critique, report, list(self.last_search_errors)
        )


async def _main() -> None:
    load_lab_env(Path(__file__).parent)
    parser = argparse.ArgumentParser(description="Run the staged arXiv research workflow.")
    parser.add_argument("question")
    parser.add_argument("--output", type=Path, default=Path("artifacts/research_report.md"))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    result = await ResearchWorkflow().run(args.question)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.report, encoding="utf-8")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(f"Report saved: {args.output}")


if __name__ == "__main__":
    asyncio.run(_main())
