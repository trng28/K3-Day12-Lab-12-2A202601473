# Day 04 Lab v2 Report — Academic Paper Research Agent

## Team

- **Room:** D303
- **Project:** Academic Paper Research Agent
- **Members:**
  - Nguyễn Mai Thanh Trúc - 2A202601473
  - Nguyễn Thị Khánh Ly - 2A202601403
  - Nguyễn Thị Tuyết Mai - 2A202601693
- **Provider/model used in recorded eval runs:** OpenAI / `gpt-4o-mini`
- **Source code:** <https://github.com/trng28/Day04-Lab-Assignment-Prompt-Engineering-Tool-Calling-Labs/tree/main/starter_v0>
- **Demo video:** <https://drive.google.com/file/d/14EGcjM6-WPPux1PsS5l0WREn42VWzfuX/view?usp=sharing>


# PHẦN A - Giới thiệu agent

## A1. Agent này làm được gì

Academic Paper Research Agent tìm metadata bài báo từ arXiv và Semantic Scholar,
lọc và xếp hạng kết quả, chọn core/supporting papers, phát hiện rủi ro khi so sánh
metric, rồi tổng hợp báo cáo có citation. Agent có giao diện React/Vite, FastAPI
NDJSON streaming API và chatbot terminal.

Workflow đang chạy:

```text
Question
  -> Planner
  -> arXiv + Semantic Scholar search
  -> Anchor filter + lexical rank + deduplication
  -> Up to 20 candidates
  -> Up to 8 core + 4 supporting papers
  -> Metadata reader
  -> Metric critic
  -> LLM synthesis or deterministic fallback
  -> Report + canonical references
```

Nếu không tìm được evidence phù hợp, agent trả về `Insufficient evidence` thay vì
tạo kết luận không có nguồn.


## A2. Tool và thành phần agent đang dùng

### Workflow chính

| Tool/thành phần | Làm được gì | Nhóm thêm? |
|---|---|---|
| `papers` / `search_arxiv` | Tìm metadata paper từ arXiv Atom API; không cần API key | Có |
| `semantic_scholar` | Tìm paper từ Semantic Scholar Academic Graph API; dùng API key | Có |
| Planner | Chọn search topic và workstream theo legal, general NLP hoặc multimodal | Có |
| Lexical ranker | Anchor filtering, relevance scoring, deduplication và role assignment | Có |
| Metadata reader | Trích metric, dataset và dấu hiệu limitation từ title/abstract | Có |
| Critic | Cảnh báo so sánh metric khi dataset/protocol không xác định hoặc khác nhau | Có |
| Synthesizer | Tổng hợp từ selected evidence, kiểm tra citation ID và thêm canonical references | Có |

Semantic Scholar được bỏ qua nếu chưa cấu hình key; arXiv vẫn tiếp tục hoạt động.
Reader hiện chưa tự động gọi `paper_text`, vì vậy không nên mô tả agent là đã đọc
toàn văn tất cả paper.

### Tool-routing eval harness

`artifacts/tools.yaml` còn khai báo `clarify`, `timeline`, `social_search`,
`lookup`, `fetch`, `format`, `send`, `policy`, `papers`, `semantic_scholar` và
`paper_text`. Đây là tool set của bài đánh giá routing. Web, social, timeline,
policy, send và full-text PDF chưa được nối vào `ResearchWorkflow`.

## A3. Câu hỏi mẫu để thử

1. `What Vietnamese pretrained language models are available?`
2. `Phân tích các bộ dữ liệu multimodal dành cho tiếng Việt.`
3. `Tìm các nghiên cứu về Vietnamese legal retrieval augmented generation.`
4. `Compare Vietnamese NLP datasets and identify open evaluation gaps.`
5. Sau khi có kết quả: `Give me the source citations.`

## A4. Kịch bản demo

| Scenario | Trace cần thấy | Giá trị thể hiện | Fallback evidence |
|---|---|---|---|
| Vietnamese pretrained models | Planner → Search → Ranking → Reader → Critic → Synthesizer | Báo cáo thay đổi theo câu hỏi và có `[P1]…[Pn]` | `assets/demo-p1.png`, `assets/demo-p2.png` |
| Vietnamese multimodal datasets | arXiv chạy theo multimodal workstreams; irrelevant papers bị anchor gate loại | Không dùng fixed legal template cho câu hỏi multimodal | Chạy lại bằng terminal chatbot |
| Semantic Scholar unavailable | Source status báo skip/error; arXiv vẫn trả kết quả | Source fallback không làm toàn workflow thất bại | `/sources` sau research run |
| Không có evidence phù hợp | Ranking trả 0; Synthesizer từ chối unsupported synthesis | Không tạo paper hoặc conclusion giả | `Insufficient evidence` report |
| Source follow-up | Câu hỏi ngắn xin source không chạy research mới | Dùng evidence của session gần nhất | `/sources` |

Các stage status được stream ngay khi workflow chạy. Nội dung report được chia
thành chunk sau khi synthesis hoàn tất; LLM provider hiện chưa stream token trực
tiếp.

---

# PHẦN B - Chi tiết và bằng chứng

## B1. Version evidence

Chỉ các run có `provider_error_cases = 0` và `measured_cases = total_cases` được
dùng để tính metric.

| Version | Prompt/tool change | Hypothesis | Metric | Before | After | Valid run |
|---|---|---|---|---:|---:|---|
| v0 | Baseline prompt | Đo routing ban đầu | Case accuracy | — | 0.65 | `runs/v0_B_base_openai_20260729T100621347234.json` |
| v1 | Run artifact dùng cùng prompt/tool hash với v0; không có change record riêng trong `version_log.csv` | Chưa đủ artifact để quy improvement cho một prompt change cụ thể | Case accuracy | 0.65 | 0.70 | `runs/v1_B_base_openai_20260729T100824375614.json` |
| v2 | Thêm explicit routing, clarification, no-tool, multi-tool, argument-preservation và send-confirmation rules | Giảm invented inputs, premature side effects và query mutation | Case accuracy | 0.70 | 0.80 | `runs/v2_B_base_openai_20260729T101324846214.json` |
| v3 | Thêm pre-call checklist về scope, completeness, side effects, coverage và fidelity | Giảm missed clarification, extra tools và argument mutation | Case accuracy | 0.80 | 0.85 | `runs/v3_B_base_openai_20260729T101547121411.json` |

Hai run sau **không hợp lệ để báo metric** vì cả 20 cases đều gặp provider error:

- `runs/v2_B_base_openai_20260729T101020089768.json`
- `runs/v3_B_base_openai_20260729T101340063068.json`

`artifacts/version_log.csv` hiện chỉ có change records cho v2 và v3. Vì vậy v1
không được diễn giải như bằng chứng nhân quả cho một thay đổi prompt cụ thể.

## B2. Failure analysis

Các failure dưới đây lấy từ valid v3 run:

| Case ID | Failure type | Actual tool calls | What failed | Proposed fix |
|---|---|---|---|---|
| `R03_web_news_routing` | `wrong_tool` | `lookup`, `social_search` | Request chỉ yêu cầu web news nhưng model gọi thêm social search | Trong prompt, nhấn mạnh “web/news alone means lookup only”; thêm negative example |
| `R11_missing_url` | `missing_info` | `clarify` | Routing đúng nhưng thiếu explicit `response_type: text` trong args | Đưa required/default-sensitive arguments vào tool description hoặc prompt example |
| `M06_switch_tool` | `wrong_tool` | `lookup`, `social_search` | User đã bỏ Twitter nhưng model vẫn giữ social tool từ turn trước | Thêm rule rằng correction mới nhất hủy source constraint cũ và thêm multi-turn example |

Ngoài routing failure, một số `tool_results` của Twitter trả HTTP 403. Những case
này có thể PASS về routing nhưng không chứng minh tool execution thành công; cần
review thủ công API key/quota trước khi demo social tools.

## B3. Team eval cases

`data/eval_group.json` có đúng 10 team-authored cases: 5 single-turn và 5
multi-turn. Suite được chạy bằng OpenAI `gpt-4o-mini`, artifact
`v3+paeea5b2d00d9+t2db7e1d172d2`.

Valid run:
`runs/v3_B_group_openai_20260729T163757156277.json`

| Case ID | What it tests | Expected tool/behavior | Result |
|---|---|---|---|
| `G01_arxiv_vietnamese_models` | Explicit arXiv source, topic and limit | `papers`, query preserved, `max_results=4` | PASS |
| `G02_semantic_scholar_legal_nlp` | Explicit Semantic Scholar source | `semantic_scholar`, query preserved, `max_results=3` | PASS |
| `G03_source_citation_policy` | Internal source/citation policy routing | `policy(policy_area=source_citation)` | FAIL — selected `data_privacy` |
| `G04_missing_paper_url` | Missing URL clarification | `clarify(response_type=text)` | FAIL — omitted explicit `response_type` |
| `G05_capability_question` | Meta question without retrieval | No tool | PASS |
| `GM01_broad_multisource_review` | Same topic across two academic sources | `papers` + `semantic_scholar` | PASS |
| `GM02_correct_academic_source` | Latest correction cancels arXiv | `semantic_scholar` only | PASS |
| `GM03_clarify_then_read_url` | Carry an explicit URL across turns | `fetch` with exact URL | PASS |
| `GM04_arxiv_fulltext_correction` | Switch from discovery to PDF extraction | `paper_text`, ID and page limit preserved | PASS |
| `GM05_require_confirmation` | No external send before confirmation | `clarify(response_type=yes_no)` | PASS |

Measured result:

| Metric | Value |
|---|---:|
| Total/measured cases | 10/10 |
| Provider error cases | 0 |
| Passed cases | 8 |
| Case accuracy | 0.80 |
| Tool routing accuracy | 1.00 |
| Argument accuracy | 0.80 |
| Multi-turn accuracy | 1.00 |

Hai failed cases đều chọn đúng tool nhưng sai hoặc thiếu argument. Không có
external publish/send nào được thực hiện trong eval.

## B4. Live chat evidence

| Scenario/turn | Version | Tool calls + args | Transcript/run | Outcome |
|---|---|---|---|---|
| Tìm 3 arXiv papers về Vietnamese pretrained models | v3 / `gpt-4o-mini` | `papers(query="Vietnamese pretrained language models", max_results=3)` | `transcripts/v3_openai_20260729T163843526848.transcript.json`, turn 1 | Answered; 3 arXiv results; tool result không có error |
| Hỏi agent có thể dùng nguồn học thuật nào | v3 / `gpt-4o-mini` | `papers(...)` + `semantic_scholar(...)` | Cùng transcript, turn 2 | Answered từ cả hai nguồn; 2 tool results không có error |

Transcript có 2 turns, 3 tool events, cả hai turn có status `answered`, không có
provider error và không có tool-result error.

Một lần chạy trước đó,
`transcripts/v3_openai_20260729T163824359325.transcript.json`, thất bại do Windows
console dùng encoding không hỗ trợ emoji/tiếng Việt. Lần chạy hợp lệ bật
`PYTHONUTF8=1`. Failure transcript được giữ để truy vết nhưng không được dùng làm
success evidence.

`samples/transcripts/example_openrouter_20260101T030000000000.transcript.json`
vẫn chỉ là sample và không được dùng làm bằng chứng của nhóm.

## B5. Tool capability evidence

| Category | Evidence file | What worked | Risk / guardrail |
|---|---|---|---|
| Must-have: arXiv paper search | `tools/papers/tool.py`, `tests/test_arxiv_tool.py` | Parse Atom metadata thành shared `Paper` model; free source fallback | Rate limit, Atom parse error; cần user agent phù hợp |
| New source: Semantic Scholar | `tools/semantic_scholar/tool.py`, `tests/test_semantic_scholar.py` | Search Academic Graph, map result và gửi `x-api-key` | HTTP 429/quota; workflow skip khi thiếu key |
| Workflow orchestration | `research_workflow.py`, `tests/test_research_workflow.py` | Plan, search, rank, read metadata, critique, synthesize và no-evidence refusal | Lexical ranking; abstract-only extraction |
| Streaming UI/API | `api.py`, `frontend/`, `tests/test_api.py` | NDJSON session/status/content/done events | Không phải token-level provider streaming |
| Optional built-ins | `tools/clarify`, `timeline`, `social_search`, `lookup`, `fetch`, `format` | Có trong eval harness và routing declarations | Không thuộc workflow chính; external API có thể lỗi |
| Bonus/local tools | `tools/policy`, `tools/paper_text`, `tools/send` | Tool implementation và declaration tồn tại | PDF chưa nối vào Reader; send cần explicit confirmation |

Không claim citation graph, dense retrieval, hybrid retrieval hoặc cross-encoder
reranking là capability hiện tại vì các phương pháp này chưa được triển khai.

## B6. Reflection

### Fix nào thuộc `system_prompt.md`?

- Source-to-tool routing và multi-source coverage.
- Quy tắc hỏi lại khi thiếu account/URL.
- No-tool boundary cho meta hoặc out-of-scope requests.
- Giữ nguyên query, timeframe, limit và correction mới nhất.
- Confirmation boundary trước external side effect.
- Pre-call checklist để giảm extra/missing tool calls.

### Fix nào thuộc `tools.yaml`?

- Mô tả tool phải nêu rõ use case và ranh giới giữa `lookup`,
  `social_search`, `timeline`, `papers` và `semantic_scholar`.
- Các argument quan trọng như `response_type` nên được mô tả rõ; không nên chỉ
  dựa vào default khi grader yêu cầu explicit value.
- Side-effect tool `send` cần mô tả rõ confirmation requirement.
- Header comment “intentionally vague” đã lỗi thời so với tool set hiện tại và
  nên được cập nhật ở version tiếp theo.

### Failure nào cần manual review?

- Tool result HTTP 403/429 hoặc provider error: routing PASS không đồng nghĩa
  execution thành công.
- Citation validation hiện kiểm tra ID/URL, chưa xác minh mọi claim với full text.
- Metric extraction từ abstract là provisional; numerical comparison cần kiểm tra
  dataset, split và protocol trong paper.

### Cải thiện tiếp theo

1. Sửa hai group-eval argument failures và ba base-eval failures, rồi chạy v4.
2. Cấu hình UTF-8 mode mặc định trong live-chat script trên Windows.
3. Chuẩn hóa `tools.yaml` descriptions và explicit required arguments.
4. Thêm full-text reading cho selected core papers, không tải toàn bộ candidates.
5. Thêm semantic/cross-encoder reranker và đánh giá quality/latency trước khi dùng.
6. Chỉ thêm citation graph sau core-paper selection để kiểm soát request cost.
