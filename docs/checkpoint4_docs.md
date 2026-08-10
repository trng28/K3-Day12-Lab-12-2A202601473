# Checkpoint 4 — Scaling & Reliability: Stateless, Readiness, Graceful Shutdown

> Block 4 của lab, mốc 11h40–12h20. File này ghi lại những gì đã sửa trong
> `app/store.py`, `app/lifecycle.py`, `app/main.py` (`/ready`); vì sao sửa
> như vậy; và một lỗi thật tìm ra khi verify bằng container (không phải chỉ
> chạy pytest).

## Kết quả

```bash
pytest tests/test_cp4.py -v
```

```
19 passed, 1 warning in 5.49s
```

Không regression CP1–CP3:

```bash
pytest tests/test_cp1.py tests/test_cp2.py tests/test_cp3.py tests/test_cp4.py -v -m "not docker"
# 68 passed, 2 deselected
```

**Lưu ý:** `app/lifecycle.py` (`install()`, `request_shutdown()`) đã được
cài đặt sớm từ Checkpoint 1 (để `uvicorn --reload` chạy được thật, xem
`docs/checkpoint1_docs.md`) — Block 4 này hoàn thiện phần còn lại:
`app/store.py` và `/ready`.

---

## Vấn đề chung của Block 4

Một instance không đủ, và instance nào cũng có thể chết bất cứ lúc nào —
cloud restart container để vá lỗi, dời máy, hoặc vì bạn deploy bản mới. Hệ
thống phải chịu được điều đó mà user không nhận ra.

---

## 1. `app/store.py` — `ConversationStore`: state ra khỏi process

### Vấn đề

```python
#  Sai — mỗi container một dict riêng
conversation_history = {}
```

Với 3 instance sau load balancer, câu hỏi 1 của user vào container A, câu
hỏi 2 vào container B. Nếu lịch sử nằm trong RAM của A thì B không biết gì
— agent "mất trí nhớ" ngẫu nhiên. Vì vậy state phải nằm ở nơi mọi instance
cùng nhìn thấy: Redis.

### Code

```python
def ping(self) -> bool:
    try:
        return bool(self.client.ping())
    except Exception:
        return False

def append(self, user_id: str, role: str, content: str) -> None:
    key = self._key(user_id)
    self.client.rpush(key, json.dumps({"role": role, "content": content}, ensure_ascii=False))
    self.client.ltrim(key, -HISTORY_MAX_MESSAGES, -1)
    self.client.expire(key, HISTORY_TTL_SECONDS)

def get_history(self, user_id: str) -> list[dict]:
    raw = self.client.lrange(self._key(user_id), 0, -1)
    return [json.loads(item) for item in raw]
```

### Giải thích từng dòng

- **`ping()`**: bọc `self.client.ping()` trong `try/except Exception`, trả
  `False` cho **bất kỳ** lỗi (mất mạng, Redis chưa khởi động, sai mật khẩu).
  Hàm này nuôi `/ready` — nếu để exception thoát ra, readiness probe sẽ
  thành lỗi `500` thay vì `503` có chủ đích, và một số orchestrator xử lý
  hai mã đó khác nhau.
- **`append()`**:
  - `rpush` — thêm vào **cuối** Redis List (thứ tự thời gian, cũ → mới).
  - `ltrim(key, -HISTORY_MAX_MESSAGES, -1)` — chỉ giữ `HISTORY_MAX_MESSAGES`
    (20) phần tử **cuối** (mới nhất). Chỉ số âm trong Redis List đếm từ
    cuối, nên `-N` tới `-1` là "N phần tử gần nhất". Không có bước này,
    prompt gửi lên LLM phình vô hạn theo thời gian — và tiền token cũng
    tăng vô hạn theo.
  - `expire(key, HISTORY_TTL_SECONDS)` (7 ngày) — hội thoại cũ tự hết hạn,
    Redis không đầy dần vô thời hạn theo số user từng gọi qua.
- **`get_history()`**: `lrange(key, 0, -1)` lấy **toàn bộ** list (đã được
  `ltrim` giới hạn từ trước), `json.loads` từng phần tử (được `append` lưu
  dưới dạng JSON string). Chưa có gì → `lrange` trả `[]` → list comprehension
  trả `[]`, không cần xử lý riêng.

### Bẫy dễ sai (đã tránh)

`ltrim(key, -N, -1)` giữ N phần tử **cuối** (mới nhất, đúng). Viết nhầm
thành `ltrim(key, 0, N-1)` sẽ giữ N phần tử **đầu** (cũ nhất) — hội thoại
"quên" tin nhắn gần đây nhất và nhớ mãi những câu chat cũ từ rất lâu.

### Test tương ứng

```bash
pytest tests/test_cp4.py::TestConversationStore -v
```

- `test_luu_va_doc_lai_duoc` — append rồi get lại đúng nội dung, đúng thứ tự
- `test_chua_co_gi_thi_tra_list_rong` — user mới → `[]`
- `test_moi_user_mot_lich_su_rieng` — key theo `user_id`
- `test_cat_bot_lich_su_qua_dai` — giữ đúng `HISTORY_MAX_MESSAGES` phần tử **mới nhất**
- `test_co_dat_han_su_dung` — TTL > 0
- `test_ping_bao_dung_trang_thai`, `test_ping_khong_nem_loi_khi_redis_chet` — `ping()` không để exception thoát ra
- `test_fake_url_tra_ve_redis_gia` — `get_redis_client("fake://")` hoạt động khi chưa có Docker

---

## 2. `/ready` trong `app/main.py`

### Vấn đề

`/health` (CP1) và `/ready` trả lời hai câu hỏi khác nhau:

| | `/health` (liveness) | `/ready` (readiness) |
|---|---|---|
| Câu hỏi | Process còn sống không? | Nhận traffic được chưa? |
| Kiểm tra dependency | **Không** | **Có** |
| Trả 503 thì sao | Orchestrator **restart** container | LB **ngừng gửi** request, không restart |

Gộp hai cái làm một là lỗi kinh điển: Redis mất kết nối 30 giây → cả 3
container đều báo unhealthy (nếu health check nhầm đi kiểm tra Redis) →
orchestrator restart cả 3 cùng lúc → khi Redis quay lại thì không còn
container nào phục vụ. Sự cố nhỏ (Redis chậm) thành sự cố toàn hệ thống
(mất trắng vài chục giây restart).

### Code

```python
@app.get("/ready")
def ready(store: ConversationStore = Depends(get_store)):
    if lifecycle.shutting_down:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    if not store.ping():
        return JSONResponse(status_code=503, content={"status": "not ready", "redis": False})
    return {"status": "ready", "redis": True}
```

### Giải thích từng dòng

- `store: ConversationStore = Depends(get_store)` — **được phép** nhận
  dependency (khác `/health`), vì đây chính xác là endpoint có nhiệm vụ
  kiểm tra dependency.
- Kiểm tra `shutting_down` **trước** `store.ping()` — đang tắt dần thì trả
  lời ngay `{"status": "shutting_down"}`, không cần tốn một lần round-trip
  tới Redis vô ích.
- `if not store.ping()` — dùng đúng **giá trị trả về** của `ping()`, không
  chỉ gọi rồi bỏ qua kết quả. Đây là lỗi phổ biến được liệt trong phần "Kẹt?
  gợi ý" của guide.

### Test tương ứng

```bash
pytest tests/test_cp4.py::TestReadiness -v
```

- `test_ready_tra_200_khi_redis_song` — Redis sống → 200
- `test_ready_tra_503_khi_redis_chet` — `store.ping()` trả `False` → 503
- `test_ready_khac_health` — `ready()` **phải** nhận dependency (ngược lại với `health()`)

---

## 3. Bằng chứng chạy thật qua container

### `/ready` khi Redis sống

```bash
curl -i http://localhost:8000/ready
```
```
HTTP/1.1 200 OK
{"status":"ready","redis":true}
```

### `/ask` — nhánh 200 OK end-to-end (còn thiếu từ Checkpoint 3, giờ đã có)

```bash
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" -H "X-User-Id: sv-demo" -d '{"question":"Docker la gi?"}'
```
```json
{"answer":"Theo mình hiểu, Docker la gi liên quan tới cách hệ thống được đóng gói và vận hành. Điểm mấu chốt là tách cấu hình ra khỏi code và giữ service ở trạng thái stateless.","user_id":"sv-demo","history_length":0,"cost_usd":2.505e-05,"tokens":{"in":3,"out":41}}
```

Ở Checkpoint 3, nhánh này trả `500` vì `store.get_history()` (CP4) chưa cài.
Giờ đã thông suốt hoàn toàn.

---

## 4. Lỗi thật phát hiện khi verify bằng container: SIGTERM không tới được `uvicorn`

Đây là phát hiện quan trọng nhất của checkpoint này — **không xuất hiện
trong pytest**, chỉ lộ ra khi test graceful shutdown bằng `docker kill` thật.

### Hiện tượng

`Dockerfile` (viết từ CP2, theo đúng gợi ý của guide) có dòng:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Kiểm tra PID 1 trong container:

```bash
docker compose exec agent cat /proc/1/cmdline
# sh -c uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

PID 1 là **`sh`**, không phải `uvicorn`. Gửi `docker kill --signal=SIGTERM`
vào container tương đương gửi SIGTERM vào PID 1 — tức là gửi vào `sh`, chứ
không phải vào tiến trình Python đang chạy `uvicorn` (một tiến trình con
khác PID).

`sh` (POSIX shell, không phải `bash`) **không tự động forward** tín hiệu
cho tiến trình con theo mặc định. Kết quả: `lifecycle.request_shutdown()`
không bao giờ được gọi, `/health` không bao giờ chuyển sang 503, và
`uvicorn` không bao giờ tự tắt — container sẽ treo tới khi orchestrator hết
kiên nhẫn (thường 10–30s) và gửi **SIGKILL**. Đây chính xác là hậu quả mà
graceful shutdown được viết ra để tránh: request đang xử lý dở bị cắt giữa
chừng, user thấy lỗi 502.

### Cách xử lý

Thêm `exec` vào lệnh shell:

```dockerfile
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

`exec` khiến `sh` **thay thế chính nó** bằng tiến trình `uvicorn` (không
fork ra tiến trình con mới) — `uvicorn` trở thành PID 1 trực tiếp, nhận
tín hiệu thẳng từ Docker.

### Xác nhận sau khi sửa

```bash
docker compose exec agent cat /proc/1/cmdline
# /usr/local/bin/python3.11 /usr/local/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Gửi SIGTERM thật:

```bash
docker kill --signal=SIGTERM <container>
```

Log container:

```
INFO:     Shutting down
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [1]
{"event": "service_stopped", "level": "info", ...}
```

Trước khi sửa, gửi tín hiệu này **không** để lại bất kỳ dòng log nào —
container tiếp tục chạy như không có gì xảy ra. Sau khi sửa, `uvicorn` tắt
sạch trong chưa tới 1 giây (app đơn giản, không có request đang xử lý dở) —
nhanh hơn cả `sleep 1` trong lúc kiểm tra tay, nên `curl` sau đó nhận `000`
(container đã đóng cổng) thay vì bắt được đúng khung `503` — nhưng đó là vì
graceful shutdown **hoàn tất quá nhanh**, không phải vì nó không chạy. Cửa
sổ 503 chính xác đã được xác nhận ở mức đơn vị bằng
`test_health_bao_503_khi_dang_tat` (gọi `request_shutdown()` trực tiếp,
không phụ thuộc thời gian thật của OS).

### Vì sao pytest không bắt được lỗi này

`test_dang_ky_handler_cho_sigterm_va_sigint` và
`test_nhuong_lai_cho_handler_cu` gọi trực tiếp `Lifecycle().install()` và
`life.request_shutdown(signal.SIGTERM, None)` **trong tiến trình pytest**,
không qua container, không qua `docker kill`, không qua lớp `sh -c`. Logic
Python hoàn toàn đúng — cái sai nằm ở **cách container khởi động tiến
trình**, một lớp nằm ngoài phạm vi mà unit test có thể chạm tới. Đây là lý
do "Thử chạy" bằng container thật (không chỉ pytest) vẫn cần thiết dù test
đã xanh hết.

---

## 5. Scale nhiều instance — giới hạn của cấu hình hiện tại

Guide gợi ý:
```bash
docker compose up -d --scale agent=3
```

Thử thật:

```
Error response from daemon: ... Bind for 0.0.0.0:8000 failed: port is already allocated
```

**Nguyên nhân:** `docker-compose.yml` khai `ports: "8000:8000"` cố định cho
service `agent`. Khi scale ra 3 replica, cả 3 đều cố bind cùng cổng `8000`
trên host — chỉ replica đầu giữ được cổng, hai replica sau lỗi ngay lúc
khởi động. Đây đúng như phần "Muốn xem load balancing thật thì bật thêm
nginx" trong guide: cổng cố định 1-1 không scale được, cần `nginx` (hoặc bỏ
mapping cổng cố định) làm lớp phân phối trước các instance thì mới scale
thật được — đó là phần điểm cộng, không thuộc phạm vi bắt buộc CP4.

Chứng minh statelessness ở **mức code** (không cần scale hạ tầng thật) đã
được `pytest` xác nhận đủ và đúng:

```python
def test_state_khong_nam_trong_process(self, fake_redis):
    container_a = ConversationStore(fake_redis)
    container_b = ConversationStore(fake_redis)
    container_a.append("u1", "user", "câu hỏi gửi vào container A")
    assert len(container_b.get_history("u1")) == 1
```

Hai `ConversationStore` khác nhau (mô phỏng 2 container) cùng thấy dữ liệu
qua Redis chung — đúng bản chất của "state ngoài process", độc lập với
việc hạ tầng Docker có scale thật được hay không.

---

## Chốt lại

| File | Hàm | Trạng thái |
|---|---|---|
| `app/store.py` | `ping()`, `append()`, `get_history()` | ✅ 8/8 test, xác nhận qua container (`/ask` 200 thật) |
| `app/main.py` | `/ready` | ✅ đúng 2 nhánh 503, khác `/health` bằng dependency |
| `app/lifecycle.py` | `install()`, `request_shutdown()` | ✅ (đã làm từ CP1), SIGTERM xác nhận thật qua `docker kill` |
| `Dockerfile` | `CMD` | 🔧 **sửa thêm**: `exec uvicorn ...` — không có `exec`, container không bao giờ graceful-shutdown được |

Checkpoint 4: **19/19 test pass**
