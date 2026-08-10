from __future__ import annotations

import argparse
import asyncio
import json
import re
import shlex
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TextIO

from env_loader import load_lab_env
from research_workflow import ResearchWorkflow, WorkflowResult
from tools.semantic_scholar.tool import semantic_scholar_api_key


ROOT = Path(__file__).parent
load_lab_env(ROOT)

HELP = """Commands:
  <question>             Run a new research workflow
  /research <question>   Run a new research workflow
  /sources               Show selected core and supporting sources
  /critique              Show comparison warnings
  /report                Print the latest report
  /save [path]           Save the latest Markdown report
  /json [path]           Save the latest structured evidence
  /help                  Show this help
  /exit                  End the chat
"""


class ResearchChatbot:
    """Conversational shell around the evidence-first research workflow."""

    def __init__(self, workflow: ResearchWorkflow | None = None) -> None:
        self.workflow = workflow or ResearchWorkflow()
        self.latest: WorkflowResult | None = None

    @staticmethod
    async def stream_text(
        text: str,
        *,
        chunk_size: int = 24,
        delay: float = 0.02,
    ) -> AsyncIterator[str]:
        """Yield small chunks so HTTP clients render a visibly progressive answer."""
        for start in range(0, len(text), chunk_size):
            yield text[start : start + chunk_size]
            if delay:
                await asyncio.sleep(delay)

    async def research_stream(self, question: str) -> AsyncIterator[str]:
        question = " ".join(question.split())
        if not question:
            yield "Please provide a research question.\n"
            return

        yield "[Planner] Decomposing the research question...\n"
        plan = self.workflow.plan(question)
        yield (
            f"[Planner] Topic: {plan.search_topic}; "
            f"{len(plan.workstreams)} workstreams.\n"
        )

        active_sources = [
            source
            for source in self.workflow.search_adapters
            if source != "semantic_scholar" or semantic_scholar_api_key()
        ]
        yield f"[Search] Querying: {', '.join(active_sources) or 'no active sources'}...\n"
        found = await self.workflow.search(plan)
        counts = ", ".join(
            f"{source}={count}"
            for source, count in self.workflow.last_source_counts.items()
            if count
        )
        yield f"[Search] Retrieved {len(found)} records{f' ({counts})' if counts else ''}.\n"

        yield "[Ranking] Deduplicating and selecting candidate papers...\n"
        evidence = self.workflow.rank(plan, found)
        yield f"[Ranking] Selected {len(evidence)} unique candidates.\n"

        yield "[Reader] Extracting datasets, methods, metrics, and limitations...\n"
        self.workflow.read(evidence)

        yield "[Critic] Checking whether reported metrics are comparable...\n"
        critique = self.workflow.critique(evidence)

        if evidence:
            yield "[Synthesizer] Generating an evidence-grounded analysis with citations...\n"
        else:
            yield "[Synthesizer] No evidence found; refusing unsupported synthesis.\n"
        report = await self.workflow.synthesize(plan, evidence, critique)
        yield "[Publisher] Formatting the final research response...\n"
        self.latest = WorkflowResult(
            plan, evidence, critique, report, list(self.workflow.last_search_errors)
        )

        core_count = sum(item.role == "core" for item in evidence)
        supporting_count = sum(item.role == "supporting" for item in evidence)
        yield (
            f"Research complete: {len(evidence)} unique candidates, "
            f"{core_count} core papers, {supporting_count} supporting sources, "
            f"{len(self.workflow.last_search_errors)} source errors.\n\n"
        )
        async for chunk in self.stream_text(report):
            yield chunk
        if report and not report.endswith("\n"):
            yield "\n"

    async def research(self, question: str) -> str:
        return "".join([chunk async for chunk in self.research_stream(question)])

    def _require_result(self) -> WorkflowResult | str:
        return self.latest or "No research result yet. Ask a question first."

    @staticmethod
    def _normalized_words(message: str) -> list[str]:
        return re.findall(r"[\w]+", message.casefold(), flags=re.UNICODE)

    def is_source_followup(self, message: str) -> bool:
        """Recognize short natural-language requests about the latest evidence."""
        if self.latest is None:
            return False
        words = self._normalized_words(message)
        if not words or len(words) > 10:
            return False
        source_words = {
            "citation", "citations", "cite", "reference", "references",
            "source", "sources", "nguồn", "dẫn",
        }
        request_words = {
            "give", "show", "list", "provide", "send", "me", "please",
            "cho", "đưa", "liệt", "kê", "trích", "xin",
        }
        return bool(set(words) & source_words) and bool(set(words) & request_words)

    def will_search(self, message: str) -> bool:
        stripped = message.strip()
        if not stripped or stripped.startswith("/"):
            return stripped.lower().startswith("/research")
        return not self.is_source_followup(stripped)

    def sources(self) -> str:
        result = self._require_result()
        if isinstance(result, str):
            return result
        selected = [
            item for item in result.evidence if item.role in {"core", "supporting"}
        ]
        if not selected:
            return "No sources were selected."
        citations: list[str] = []
        for index, item in enumerate(selected, start=1):
            authors = ", ".join(item.paper.authors[:3]) or "Unknown author"
            if len(item.paper.authors) > 3:
                authors += ", et al."
            year = item.paper.published_at[:4] or "n.d."
            citations.append(
                f"{index}. {authors} ({year}). "
                f"[{item.paper.title}]({item.paper.source_url}). "
                f"{item.role.capitalize()} source."
            )
        return "\n".join(citations)

    def critique(self) -> str:
        result = self._require_result()
        if isinstance(result, str):
            return result
        notes = [*result.critique.warnings, *result.critique.comparison_rules]
        return "\n".join(f"- {note}" for note in notes) or "No warnings."

    def report(self) -> str:
        result = self._require_result()
        return result if isinstance(result, str) else result.report

    def save(self, path: str | None = None, *, structured: bool = False) -> str:
        result = self._require_result()
        if isinstance(result, str):
            return result
        default = (
            Path("artifacts/research_chat_result.json")
            if structured
            else Path("artifacts/research_chat_report.md")
        )
        output = Path(path) if path else default
        output.parent.mkdir(parents=True, exist_ok=True)
        if structured:
            output.write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            output.write_text(result.report, encoding="utf-8")
        return f"Saved: {output.resolve()}"

    async def respond(self, message: str) -> str:
        return "".join([chunk async for chunk in self.respond_stream(message)])

    async def respond_stream(self, message: str) -> AsyncIterator[str]:
        message = message.strip()
        if not message:
            return
        if not message.startswith("/"):
            if self.is_source_followup(message):
                yield self.sources()
                return
            async for chunk in self.research_stream(message):
                yield chunk
            return

        try:
            parts = shlex.split(message, posix=False)
        except ValueError as exc:
            yield f"Invalid command: {exc}"
            return
        command = parts[0].lower()
        argument = " ".join(parts[1:]).strip().strip('"') or None

        if command == "/research":
            async for chunk in self.research_stream(argument or ""):
                yield chunk
            return
        if command == "/sources":
            yield self.sources()
        elif command == "/critique":
            yield self.critique()
        elif command == "/report":
            async for chunk in self.stream_text(self.report()):
                yield chunk
        elif command == "/save":
            yield self.save(argument)
        elif command == "/json":
            yield self.save(argument, structured=True)
        elif command == "/help":
            yield HELP
        else:
            yield f"Unknown command: {command}\n\n{HELP}"


async def run_chat(
    chatbot: ResearchChatbot,
    *,
    input_stream: TextIO | None = None,
) -> None:
    print("Academic Paper Research Agent")
    print("Ask a research question, or type /help. Type /exit to stop.")

    while True:
        try:
            if input_stream is None:
                message = await asyncio.to_thread(input, "\nYou> ")
            else:
                message = input_stream.readline()
                if not message:
                    break
                print(f"\nYou> {message.rstrip()}")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if message.strip().lower() in {"/exit", "/quit"}:
            break
        try:
            print("\nAgent> ", end="", flush=True)
            async for chunk in chatbot.respond_stream(message):
                print(chunk, end="", flush=True)
            print()
        except Exception as exc:
            print(f"Research failed: {type(exc).__name__}: {exc}")


async def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive chatbot for the staged research workflow."
    )
    parser.add_argument(
        "--question",
        help="Run one question non-interactively and exit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Save the one-shot report to this path.",
    )
    args = parser.parse_args()

    chatbot = ResearchChatbot()
    if args.question:
        async for chunk in chatbot.respond_stream(args.question):
            print(chunk, end="", flush=True)
        print()
        if args.output:
            print(chatbot.save(str(args.output)))
        return
    await run_chat(chatbot)


if __name__ == "__main__":
    asyncio.run(_main())
