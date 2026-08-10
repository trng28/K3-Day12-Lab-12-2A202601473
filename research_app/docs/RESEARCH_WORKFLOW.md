# Research workflow agent

> The primary setup and scoring guideline is now
> [`../README.md`](../README.md). This document contains additional workflow
> implementation notes.

The workflow is a staged evidence pipeline rather than one large prompt:

```text
Planner
  -> Search adapters (arXiv + Semantic Scholar now; web, GitHub, social later)
  -> Deduplicate and rank 20 candidates
  -> Select 8 core + 4 supporting sources
  -> Reader extracts dataset, method, metric, limitation
  -> Citation-graph expansion (adapter extension point)
  -> Critic checks whether numerical comparisons are valid
  -> Synthesizer/Publisher writes the report and experiment backlog
```

`research_workflow.py` searches arXiv and Semantic Scholar concurrently. Every
additional source can be added as an async function with the same signature:

```python
async def search_source(query: str, max_results: int) -> list[Paper]:
    ...

workflow = ResearchWorkflow({
    "arxiv": search_arxiv,
    "semantic_scholar": search_semantic_scholar,
    "github": search_github,
})
```

The shared `Paper` model prevents the ranking and reading stages from depending on
provider-specific response shapes. Source adapters should preserve a stable ID,
canonical URL, authors, dates, abstract/snippet, and categories.

Set the Semantic Scholar key in `.env`:

```dotenv
SEMANTIC_SCHOLAR_API_KEY=your-key
```

For compatibility, `SEMANTIC_SCHOLAR_API` and the misspelled
`SEMATIC_SCHOLAR_API` are also accepted. The canonical variable is recommended.

## Run

```powershell
python research_workflow.py "Vietnamese legal retrieval augmented generation"
```

The default report is written to `artifacts/research_report.md`. Add
`--json-output artifacts/research_report.json` to retain structured evidence.

## Chatbot

Start an interactive session:

```powershell
.\scripts\run_research_chat.ps1
```

Every plain-language question starts a new research run. Afterward, use `/sources`,
`/critique`, `/report`, `/save`, or `/json` to inspect and persist the result.
The bot uses arXiv directly and does not require an LLM API key.

The terminal response is streamed. While live APIs are running, the chatbot emits
`Planner`, `Search`, `Ranking`, `Reader`, `Critic`, and `Publisher` status events,
then writes the completed report incrementally.

## Web application

The web stack consists of:

- FastAPI at `http://localhost:8000`, with interactive docs at `/docs`.
- React/Vite development UI at `http://localhost:5173`.
- Dockerized Nginx UI at `http://localhost:8080`.
- Streaming `POST /api/chat/stream` responses using NDJSON.

Deploy the complete stack:

```powershell
.\scripts\run_web.ps1 -Build
```

Stop it without deleting the saved report/PDF volumes:

```powershell
.\scripts\stop_web.ps1
```

For local development, run the backend and frontend in separate terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --reload
cd frontend
npm install
npm run dev
```

For a one-shot run:

```powershell
.\scripts\run_research_chat.ps1 `
  -Question "Vietnamese legal retrieval augmented generation" `
  -Output "artifacts\vietnamese_legal_rag.md"
```

## Test

From `starter_v0`:

```powershell
.\scripts\test_research_workflow.ps1
```

Or from Command Prompt:

```bat
scripts\test_research_workflow.cmd
```

The script uses `.venv`, installs `pytest` when it is missing, runs the focused
workflow tests, and performs a Python compilation check. Pass `-SkipInstall` when
dependencies are managed separately.

## Deliberate boundaries

- Metadata extraction is conservative. Full-text reading should use `paper_text`
  for selected core papers, not all candidates.
- Citation-graph expansion belongs after core-paper selection to control cost.
- A metric name alone is not comparable evidence. Dataset, split, retrieval depth,
  relevance labels, and protocol must all match.
- Publishing to an external destination remains behind the existing confirmation
  boundary. This workflow only writes local artifacts.
