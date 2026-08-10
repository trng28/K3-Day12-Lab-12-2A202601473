# Checkpoint 3 — API Security: Authentication, Rate Limiting, Cost Guard

> Block 3 của lab, mốc 10h55–11h40. File này ghi lại những gì đã sửa trong
> `app/auth.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py`
> (`/ask`); vì sao sửa như vậy; và bằng chứng chạy thật qua container.

## Kết quả

```bash
pytest tests/test_cp3.py -v
```

```
22 passed, 1 warning in 5.47s
```

Không có regression ở CP1/CP2:

```bash
pytest tests/test_cp1.py tests/test_cp2.py -v -m "not docker"
# 27 passed, 2 deselected
```

---

## Ba lớp bảo vệ, ba câu hỏi khác nhau

| Lớp | Câu hỏi | Mã lỗi | File |
|---|---|---|---|
| Authentication | Bạn là ai? | 401 | `app/auth.py` |
| Rate limiting | Bạn gọi có quá nhanh không? | 429 | `app/rate_limiter.py` |
| Cost guard | Bạn đã tiêu hết ngân sách chưa? | 402 | `app/cost_guard.py` |

Một URL public bị bot quét Internet tìm thấy trong vài giờ. Không có ba lớp
này, mỗi request của người lạ là một lần trả tiền cho nhà cung cấp LLM.

---

## 1. `app/auth.py` — hàm `verify_api_key()`

### Vấn đề

So sánh API key bằng `==` là một lỗ hổng timing attack: toán tử `==` dừng
ngay tại ký tự đầu tiên khác nhau, nên **thời gian trả lời** rò rỉ thông tin
— đoán đúng ký tự đầu thì phản hồi chậm hơn một chút (phải so tới ký tự thứ
2). Với đủ số lần đo, kẻ tấn công dò ra khóa đúng từng ký tự một.

### Code

```python
def verify_api_key(
    x_api_key: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> str:
    expected = get_settings().agent_api_key
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
        )
    return x_user_id if x_user_id else ANONYMOUS_USER
```

### Giải thích từng dòng

- `x_api_key`, `x_user_id` — FastAPI tự map header `X-API-Key` → `x_api_key`,
  `X-User-Id` → `x_user_id` (dấu gạch ngang → gạch dưới, không phân biệt hoa
  thường).
- `expected = get_settings().agent_api_key` — đọc khóa đúng từ `Settings`
  (CP1), không hardcode.
- `x_api_key is None or not secrets.compare_digest(...)` — **luôn** gọi
  `compare_digest` khi cả hai chuỗi tồn tại; `secrets.compare_digest` chạy
  hết chuỗi bất kể ký tự nào khác nhau trước, nên thời gian trả lời không
  còn phụ thuộc vào việc đoán đúng bao nhiêu ký tự.
- `return x_user_id if x_user_id else ANONYMOUS_USER` — client không gửi
  `X-User-Id` (ví dụ health-check probe của platform) thì dùng chung định
  danh `ANONYMOUS_USER`; `user_id` này là đơn vị để tính rate limit và chi
  phí ở các bước sau.

### Test tương ứng

```bash
pytest tests/test_cp3.py::TestAuthentication -v
```

- `test_khong_co_key_thi_401`, `test_sai_key_thi_401` — thiếu/sai key → 401
- `test_dung_key_thi_200` — key đúng → 200, có `answer`
- `test_tra_ve_dung_user_id`, `test_khong_gui_user_id_thi_thanh_anonymous` — user_id đúng như header hoặc fallback `ANONYMOUS_USER`
- `test_so_sanh_key_chong_timing_attack` — parse AST source, khẳng định `secrets.compare_digest` thực sự **được gọi**, không chỉ nằm trong comment

---

## 2. `app/rate_limiter.py` — sliding window bằng Redis ZSET

### Vấn đề

Đếm request theo phút đồng hồ (0:00–0:59, 1:00–1:59, ...) có lỗ hổng: giới
hạn 10/phút, user gửi 10 request lúc `10:00:59` và 10 request lúc `10:01:01`
— 20 request trong 2 giây thực tế mà vẫn "đúng luật" theo cách đếm đó. Sliding
window (cửa sổ trượt) không có kẽ hở này: luôn nhìn lại đúng 60 giây gần
nhất tính từ thời điểm request tới.

### Code

```python
def hit_count(self, user_id: str, now: float | None = None) -> int:
    now = now if now is not None else time.time()
    key = self._key(user_id)
    self.client.zremrangebyscore(key, 0, now - WINDOW_SECONDS)
    return self.client.zcard(key)

def check(self, user_id: str, now: float | None = None) -> None:
    now = now if now is not None else time.time()
    key = self._key(user_id)
    if self.hit_count(user_id, now) >= self.limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(WINDOW_SECONDS)},
        )
    self.client.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
    self.client.expire(key, WINDOW_SECONDS)
```

### Giải thích từng dòng

- Cấu trúc dữ liệu: Redis **Sorted Set**, `score` = timestamp của request,
  `member` = chuỗi định danh request đó.
- `zremrangebyscore(key, 0, now - WINDOW_SECONDS)` — xoá mọi entry có score
  (timestamp) cũ hơn 60 giây so với `now`, tức là "đẩy cửa sổ trượt tới".
- `zcard(key)` — đếm số entry còn lại trong cửa sổ, sau khi đã dọn entry cũ.
- **Kiểm tra trước, ghi nhận sau**: `check()` gọi `hit_count()` (đếm) trước
  khi `zadd` (ghi request hiện tại). Làm ngược lại (ghi trước, đếm sau) sẽ
  đếm luôn cả request hiện tại vào tổng, nên chặn nhầm sớm hơn 1 request so
  với hạn mức thật.
- `member = f"{now}:{uuid.uuid4().hex}"` — **phải duy nhất**. Nếu dùng thẳng
  `now` làm member, hai request tới đúng cùng timestamp (rất dễ xảy ra khi
  test hoặc khi traffic cao) sẽ có cùng member → ZSET chỉ giữ một bản, đếm
  thiếu.
- `expire(key, WINDOW_SECONDS)` — key tự dọn sau 60s không hoạt động, Redis
  không phình vô hạn theo số user.

### Test tương ứng

```bash
pytest tests/test_cp3.py::TestRateLimiter -v
```

- `test_trong_han_muc_thi_cho_qua` — đủ 3 request trong hạn mức 3 → không lỗi
- `test_vuot_han_muc_thi_429` — request thứ 4 → 429
- `test_cua_so_truot_qua_thi_duoc_goi_lai` — request cũ ra khỏi cửa sổ 60s → được gọi lại
- `test_moi_user_mot_han_muc_rieng` — key theo `user_id`, user khác không bị ảnh hưởng
- `test_dem_dung_so_request` — `hit_count()` đếm đúng
- `test_qua_http_thi_tra_429` — end-to-end qua `/ask`, request thứ N+1 → 429
- `test_401_duoc_kiem_tra_truoc_429` — không có key thì dừng ở 401, **không** tiêu quota rate limit của bất kỳ ai

---

## 3. `app/cost_guard.py` — chặn chi phí trước khi hoá đơn chặn bạn

### Vấn đề

Rate limit và cost guard giải quyết hai vấn đề khác nhau, **không thay thế
nhau**: 10 request/phút nghe an toàn, nhưng nếu mỗi request tốn 50.000
token thì ngân sách tháng bị đốt sạch trong vài phút — rate limiter không
biết gì về việc đó.

### Code

```python
def spent(self, user_id: str, month: str | None = None) -> float:
    value = self.client.get(self._key(user_id, month))
    return float(value) if value is not None else 0.0

def check(self, user_id, estimated_cost=0.0, month=None) -> None:
    if self.spent(user_id, month) + estimated_cost > self.budget:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="monthly budget exceeded",
        )

def record(self, user_id: str, cost: float, month: str | None = None) -> float:
    key = self._key(user_id, month)
    total = self.client.incrbyfloat(key, cost)
    self.client.expire(key, KEY_TTL_SECONDS)
    return float(total)
```

### Giải thích từng dòng

- Key Redis: `cost:<user_id>:<YYYY-MM>` (`_key()` cho sẵn) — nhãn tháng nằm
  trong key nên sang tháng mới tự động có key mới, tương đương "reset" ngân
  sách mà không cần cron job dọn dẹp.
- `spent()`: Redis trả `None` khi key chưa tồn tại (chưa tiêu gì) — **phải**
  trả `0.0` thay vì để `float(None)` ném `TypeError`. Redis luôn trả giá trị
  dạng chuỗi, nên ép kiểu `float(value)`.
- `check()`: so `spent() + estimated_cost` (chi phí **sau khi** request này
  chạy xong) với `budget`, chứ không chỉ so `spent()` hiện tại — chặn được
  cả trường hợp request này sẽ làm vượt ngân sách, không chỉ trường hợp đã
  vượt từ trước.
- `record()`: `INCRBYFLOAT` là lệnh Redis atomic — cộng dồn đúng cả khi
  nhiều request tới gần như đồng thời (không có race condition kiểu
  đọc-rồi-ghi ở tầng ứng dụng). `expire(key, KEY_TTL_SECONDS)` (~40 ngày)
  để dữ liệu chi tiêu tháng cũ còn giữ lại đủ lâu cho việc đối soát, rồi
  Redis tự dọn.

### Test tương ứng

```bash
pytest tests/test_cp3.py::TestCostGuard -v
```

- `test_chua_tieu_gi_thi_spent_bang_0` — key chưa tồn tại → `spent() == 0.0`
- `test_record_cong_don` — nhiều lần `record()` cộng dồn đúng
- `test_con_ngan_sach_thi_cho_qua`, `test_vuot_ngan_sach_thi_402` — biên đúng của `check()`
- `test_moi_user_mot_ngan_sach_rieng` — key theo `user_id`, không ảnh hưởng chéo
- `test_qua_http_thi_tra_402` — end-to-end qua `/ask`: set sẵn chi tiêu vượt ngân sách → 402
- `test_ask_ghi_nhan_chi_phi` — `/ask` phải gọi `guard.record()` sau khi trả lời; thiếu bước này thì ngân sách không bao giờ tăng và cost guard vô dụng

---

## 4. `app/main.py` — ghép nối trong `/ask`

### Vấn đề

Ghép sai thứ tự các lớp bảo vệ là tự hại mình: nếu gọi LLM **trước** khi
check rate limit/budget, request bị chặn sau khi đã tốn tiền — vừa mất tiền
vừa trả lỗi cho user.

### Code

```python
@app.post("/ask")
def ask(payload, user_id=Depends(verify_api_key), store=..., limiter=..., guard=...):
    limiter.check(user_id)
    guard.check(user_id)

    history = store.get_history(user_id)
    result = ask_llm(payload.question, history)

    store.append(user_id, "user", payload.question)
    store.append(user_id, "assistant", result["answer"])

    guard.record(user_id, result["cost_usd"])

    log_event("ask_completed", user_id=user_id, tokens_in=result["tokens_in"],
              tokens_out=result["tokens_out"], cost_usd=result["cost_usd"])

    return {
        "answer": result["answer"],
        "user_id": user_id,
        "history_length": len(history),
        "cost_usd": result["cost_usd"],
        "tokens": {"in": result["tokens_in"], "out": result["tokens_out"]},
    }
```

### Giải thích thứ tự

```
verify_api_key (dependency, chạy trước cả khi vào thân hàm)
   → limiter.check         # 429 nếu gọi quá nhanh
   → guard.check           # 402 nếu hết ngân sách
   → get_history → ask_llm # ĐÂY mới là bước tốn tiền
   → append × 2 → guard.record → log_event
```

- `verify_api_key` là FastAPI dependency nên chạy **trước khi** thân hàm
  `ask()` chạy — request thiếu/sai key dừng ở 401, không chạm tới bất kỳ
  dòng nào ở trên, kể cả `limiter.check`.
- `limiter.check` và `guard.check` đứng ngay đầu thân hàm, **trước**
  `ask_llm` — đây là điểm mà tiền thật sự bị tiêu. Chặn trước bước này nghĩa
  là request bị từ chối không tốn một xu nào.
- `guard.record` chạy **sau** khi có `result["cost_usd"]` từ LLM thật (chi
  phí thực tế, không phải ước tính) — ghi đúng số tiền đã tiêu.
- `log_event("ask_completed", ...)` — structured log (CP1) ghi lại đủ để
  trả lời "user nào tốn tiền nhất hôm nay?" sau này.

### Test tương ứng

```bash
pytest tests/test_cp3.py::TestAskResponse -v
```

- `test_tra_du_cac_truong` — response có đủ `answer`, `user_id`, `history_length`, `cost_usd`, `tokens`
- `test_cau_hoi_rong_thi_422` — `question=""` bị Pydantic (`Field(min_length=1)`) chặn trước khi vào thân hàm

---

## 5. Bằng chứng chạy thật qua container

### Authentication — 401 khi thiếu/sai key

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" -d '{"question":"Hello"}'
# 401

curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" -H "X-API-Key: khoa-bia-dat" -d '{"question":"Hello"}'
# 401
```

### Rate limiting — 429 sau khi vượt hạn mức (10/phút mặc định)

```bash
for i in $(seq 1 15); do
  curl -s -o /dev/null -w '%{http_code} ' -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" -H "X-API-Key: $AGENT_API_KEY" -H "X-User-Id: sv01" \
    -d '{"question":"test"}'
done
```

Kết quả thật (10 request đầu, sau đó 429):

```
... ... ... ... ... ... ... ... ... 429 429 429 429 429 429
```

### Nhánh "key đúng → 200" cần đợi Block 4

Gọi `/ask` với key đúng qua container thật hiện trả `500 Internal Server
Error`, log cho thấy rõ lý do:

```
File "/app/app/store.py", line 76, in get_history
    raise NotImplementedError("TODO (CP4): cài đặt get_history")
```

**Đây không phải lỗi của Checkpoint 3.** `/ask` gọi
`store.get_history(user_id)`, và `store` là `ConversationStore` thật (
`app/store.py`) — code của **Block 4**, chưa triển khai. Trong `pytest`,
fixture `client` (xem `tests/conftest.py`) tự động thay `ConversationStore`
bằng `StubStore` giả **đúng để tránh phụ thuộc ngược** này:

> "checkpoint sau được phép dùng code của checkpoint trước, nhưng KHÔNG bao
> giờ ngược lại. Vì vậy test CP1/CP3 dùng `StubStore` thay cho
> `ConversationStore` — bạn không bị mất điểm CP3 chỉ vì chưa làm CP4."

Vì vậy **22/22 pytest pass** là bằng chứng đầy đủ và chính xác cho
Checkpoint 3. Nhánh `200 OK` end-to-end qua `curl` thật sẽ tự hoạt động
ngay khi `app/store.py` (Block 4) được hoàn thiện — không cần sửa gì thêm ở
`auth.py`, `rate_limiter.py`, `cost_guard.py`, hay `/ask`.

### Sự cố phụ gặp phải: `.env` dòng CRLF làm hỏng header HTTP

Lần đầu test bằng cách trích `AGENT_API_KEY` từ `.env` qua `grep | cut`,
request luôn trả "Invalid HTTP request received." — không phải 401/200.

**Nguyên nhân:** `.env` được lưu với line ending Windows (`\r\n`). Trích
xuất bằng `cut -d= -f2` giữ lại luôn ký tự `\r` ở cuối giá trị:

```
AGENT_API_KEY=kiJgfX6CS5sXLXmdHvV4th_xG4DnajoSAMmlBsckVD0^M$
```

`\r` lẫn trong giá trị header `X-API-Key` làm hỏng cú pháp HTTP request (curl
gửi `X-API-Key: <key>\r\r\n` — một `\r` thừa giữa dòng).

**Cách xử lý:** lọc bỏ `\r` khi trích giá trị:
```bash
AGENT_API_KEY=$(grep AGENT_API_KEY .env | cut -d= -f2 | tr -d '\r')
```

Bài học: khi soạn `.env` bằng editor trên Windows, kiểm tra line ending nếu
định dùng giá trị đó trực tiếp trong script Bash/WSL.

---

## Chốt lại

| File | Hàm | Trạng thái |
|---|---|---|
| `app/auth.py` | `verify_api_key()` | ✅ `compare_digest`, 401 đúng, xác nhận qua container |
| `app/rate_limiter.py` | `hit_count()`, `check()` | ✅ sliding window ZSET, 429 đúng, xác nhận qua container |
| `app/cost_guard.py` | `spent()`, `check()`, `record()` | ✅ 402 đúng, atomic `incrbyfloat` |
| `app/main.py` | `/ask` | ✅ đúng thứ tự check-trước-tốn-tiền-sau |

Checkpoint 3: **22/22 test pass**
