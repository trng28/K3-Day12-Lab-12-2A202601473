# Checkpoint 1: 12-Factor Config, Health Check & Structured Logging

> Block 1 của lab, mốc 9h20–10h00. File này ghi lại những gì đã làm, vì sao
> làm như vậy, và cách chạy lại để kiểm tra.

## Kết quả

```bash
pytest tests/test_cp1.py -v
```

```
13 passed, 1 warning in 5.53s
```

**Lưu ý môi trường:** `.venv` của repo này được tạo trong WSL (Linux). Chạy
`pytest`/`uvicorn` phải thực hiện **từ trong WSL**, không phải PowerShell hay
Git Bash trên Windows, nếu không sẽ lấy nhầm Python hệ thống và thiếu
`redis`, `fakeredis`.

```bash
wsl
cd /mnt/d/vinuni-lab/K3-Day12-Lab-12-2A202601473
source .venv/bin/activate
pytest tests/test_cp1.py -v
```

---

## 1. `app/config.py` class `Settings`

### Vấn đề

Config nằm trong code (hardcode key, hardcode port...) nghĩa là cùng một dòng
code chạy khác nhau ở mỗi môi trường muốn sửa lại phải build lại image. Đây
là điều 12-Factor App cấm: *code giống nhau ở mọi môi trường, chỉ config khác
nhau — nên config phải nằm ngoài code.*

### Code

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    port: int = 8000
    agent_api_key: str
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_per_minute: int = 10
    monthly_budget_usd: float = 10.0
    log_level: str = "INFO"
```

### Giải thích từng dòng

| Trường | Mặc định | Vì sao |
|---|---|---|
| `port` | `8000` | Không phải secret, dev chạy local ngay không cần set gì |
| `agent_api_key` | **không có** | Là secret — thiếu biến `AGENT_API_KEY` phải làm app **chết ngay lúc khởi động** (`ValidationError`), không được âm thầm chạy tiếp rồi phục vụ request miễn phí bằng khóa mặc định |
| `redis_url` | `redis://localhost:6379/0` | Chạy local không cần set, nhưng trong `docker-compose.yml` được override thành `redis://redis:6379/0` (tên service, không phải `localhost`) |
| `rate_limit_per_minute` | `10` | Dùng ở Block 3 |
| `monthly_budget_usd` | `10.0` | Dùng ở Block 3 |
| `log_level` | `"INFO"` | Dùng cho logging |

`pydantic-settings` tự map tên trường viết thường sang biến môi trường viết
hoa: `agent_api_key` ← đọc từ biến `AGENT_API_KEY`.

### Test tương ứng

```bash
pytest tests/test_cp1.py::TestConfig -v
```

- `test_settings_co_du_cac_truong` — đủ 6 trường
- `test_doc_gia_tri_tu_bien_moi_truong` — set env → giá trị đổi theo, không sửa code
- `test_gia_tri_mac_dinh_hop_ly` — 5 trường không phải secret dùng được ngay không cần set gì
- `test_thieu_api_key_thi_fail_fast` — thiếu `AGENT_API_KEY` → `ValidationError`
- `test_khong_hardcode_secret` — quét `config.py`, `main.py`, `auth.py` không có secret hardcode (`sk-`, `AKIA`, ...)

---

## 2. `app/logging_utils.py`, hàm `log_event()`

### Vấn đề

`print(f"user {uid} hỏi {question}")` là log viết cho người đọc bằng mắt.
Cloud (Railway, Render, Datadog...) đọc log bằng máy — cần **một dòng = một
JSON object** để lọc, đếm, và cảnh báo được (ví dụ: "user nào tốn tiền nhất
hôm nay?", "tỷ lệ lỗi 5 phút qua?").

### Code

```python
def log_event(event: str, level: str = "info", **fields) -> str:
    payload = {
        "event": event,
        "level": level.lower(),
        "timestamp": utc_now_iso(),
        **fields,
    }
    line = json.dumps(payload, ensure_ascii=False)
    print(line, file=sys.stdout)
    return line
```

### Giải thích từng dòng

- `payload` — dict với 3 khóa bắt buộc (`event`, `level`, `timestamp`) rồi gộp
  thêm mọi keyword argument tuỳ ý (`user_id`, `cost_usd`, ...) qua `**fields`.
- `level.lower()` — chuẩn hoá mức log về chữ thường, để `"ERROR"` và `"error"`
  không tạo ra hai giá trị khác nhau khi filter log trên cloud.
- `json.dumps(payload, ensure_ascii=False)` — **không** truyền `indent`: JSON
  phải nằm gọn trên **một dòng**, vì hệ thống gom log theo dòng (mỗi dòng =
  một record); xuống dòng giữa JSON là một log bị vỡ thành nhiều mảnh vô
  nghĩa. `ensure_ascii=False` để tiếng Việt in ra đúng (`"hỏi"`) chứ không bị
  escape thành `"hỏi"`.
- `print(line, file=sys.stdout)` — in ra stdout, nơi cloud thu log.
- `return line` — trả lại chuỗi đã in, để test hoặc caller có thể kiểm tra
  lại nếu cần.

### Test tương ứng

```bash
pytest tests/test_cp1.py::TestStructuredLogging -v
```

- `test_log_event_tra_ve_json_hop_le` — parse được JSON, có `event`, `level`, `timestamp`
- `test_log_event_gan_them_truong_tuy_y` — `**fields` (`user_id`, `cost_usd`) đi vào đúng JSON
- `test_level_luon_viet_thuong` — `"ERROR"` → `"error"`
- `test_log_ra_stdout_dung_mot_dong` — stdout chỉ có đúng 1 dòng
- `test_timestamp_dung_dinh_dang_iso` — timestamp khớp định dạng ISO-8601

---

## 3. `app/main.py`, hàm `health()`

### Vấn đề

`/health` là **liveness probe**: orchestrator (Docker, Railway, K8s) gọi định
kỳ để quyết định "process này có cần restart không?". Nếu hàm này gọi Redis
hay bất kỳ dependency nào, một lần Redis nấc là cả cụm container bị restart
theo — biến sự cố nhỏ (Redis chậm 1 nhịp) thành sự cố lớn (toàn bộ service
down trong lúc restart).

### Code

```python
@app.get("/health")
def health():
    if lifecycle.shutting_down:
        return JSONResponse(status_code=503, content={"status": "shutting_down"})
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}
```

### Giải thích từng dòng

- Hàm **không nhận tham số nào** (không `Depends(...)`) — đây là điểm test
  kiểm tra trực tiếp bằng `inspect.signature`, vì đó là cách duy nhất đảm bảo
  chắc chắn `/health` không lỡ tay chạm Redis/DB.
- `lifecycle.shutting_down` — cờ do `app/lifecycle.py` (CP4) quản lý. Khi
  process nhận `SIGTERM` để chuẩn bị tắt, cờ này bật lên, `/health` trả `503`
  để load balancer rút container ra khỏi vòng xoay trước khi nó bị kill hẳn.
- Bình thường (`shutting_down = False`) → trả `200` mặc định của FastAPI với
  `status`, `service`, `version` — đủ để orchestrator biết process còn sống.

### Test tương ứng

```bash
pytest tests/test_cp1.py::TestHealthEndpoint -v
```

- `test_health_tra_ve_200` — gọi bình thường → `200`, `status == "ok"`
- `test_health_khong_can_api_key` — không gửi `X-API-Key` vẫn `200` (probe của platform không có key)
- `test_health_khong_phu_thuoc_dependency_nao` — `health()` không có tham số dependency nào

---

## Chạy thử tay

```bash
uvicorn app.main:app --reload --port 8000
curl -i http://localhost:8000/health
```

Kết quả:

```
(.venv) trucnmt@LAPTOP-R6CN042B:/mnt/d/vinuni-lab/K3-Day12-Lab-12-2A202601473$  curl -i http://localhost:8000/health
HTTP/1.1 200 OK
date: Mon, 10 Aug 2026 03:17:17 GMT
server: uvicorn
content-length: 57
content-type: application/json

{"status":"ok","service":"day12-agent","version":"1.0.0"
```

### Lưu ý: cần `app/lifecycle.py` (CP4) để `uvicorn` chạy được thật

`main.py`'s `lifespan()` gọi `lifecycle.install()` lúc khởi động. Pytest
không kích hoạt lifespan này nên CP1 pass được dù `lifecycle.py` còn
`NotImplementedError` — nhưng chạy `uvicorn` thật thì crash ngay:

```
NotImplementedError: TODO (CP4): cài đặt install
```

Vì guide cho phép viết phần này sớm ("Phần 503 thuộc CP4, nhưng viết luôn
bây giờ cũng được"), đã cài đặt luôn `install()` và `request_shutdown()`
trong `app/lifecycle.py` để `uvicorn --reload` chạy được và `/health` trả
lời thật qua `curl`, không chỉ qua `TestClient` trong pytest.

## Chốt lại

| File | Hàm/Class | Trạng thái |
|---|---|---|
| `app/config.py` | `Settings` | ✅ 6 trường, `agent_api_key` không mặc định |
| `app/logging_utils.py` | `log_event()` | ✅ 1 dòng JSON, `ensure_ascii=False` |
| `app/main.py` | `health()` | ✅ không dependency, xử lý cả 2 nhánh (ok / shutting_down) |

Checkpoint 1: **13/13 test pass** 
