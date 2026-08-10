# Checkpoint 2 - Docker: Multi-Stage Build, Bảo Mật Image, Compose Stack

> Block 2 của lab, mốc 10h00–10h45. File này ghi lại những gì đã sửa trong
> `Dockerfile`, `.dockerignore`, `docker-compose.yml`; vì sao sửa như vậy;
> và bằng chứng chạy thật (build + compose up), không chỉ chạy pytest.

## Kết quả

```bash
pytest tests/test_cp2.py -v
```

```
16 passed in 4.36s
```

Toàn bộ 16 test pass, **bao gồm** 2 test có mark `docker` (`test_build_thanh_cong`,
`test_image_du_nho`) — nghĩa là `docker build` thật đã chạy thành công và
image nằm dưới ngưỡng 500MB, không chỉ là cấu trúc file đúng cú pháp.

```bash
docker images day12-agent:prod
```

```
IMAGE               ID           DISK USAGE   CONTENT SIZE
day12-agent:prod   79bc610e703e   270MB         63.7MB
```

**Lưu ý môi trường:** chạy `docker build`, `docker compose`, `pytest` đều
phải từ **WSL** (`.venv` là venv Linux), không phải PowerShell/Git Bash
Windows.

> **Cập nhật ở Checkpoint 4:** dòng `CMD` dưới đây ban đầu thiếu `exec`,
> khiến PID 1 trong container là `sh` chứ không phải `uvicorn` — SIGTERM
> không tới được tiến trình Python, graceful shutdown không hoạt động dù
> đã cài `app/lifecycle.py`. Lỗi này không lộ ra ở Checkpoint 2 (chưa test
> graceful shutdown ở đây), chỉ phát hiện được khi verify CP4 bằng
> `docker kill` thật. Xem chi tiết ở `docs/checkpoint4_docs.md` mục 4. Nội
> dung `CMD` dưới đây đã được cập nhật để phản ánh bản sửa cuối cùng.

---

## 1. `Dockerfile` — multi-stage build

### Vấn đề

Dockerfile ban đầu (`FROM python:3.11`, 1 stage, `COPY . .` trước
`pip install`, không `USER`, không `HEALTHCHECK`, cổng cố định `8000`) chạy
được nhưng vi phạm gần hết nguyên tắc production:

- Base image đầy đủ (`python:3.11`) nặng ~1GB.
- `COPY . .` đứng trước `pip install` → sửa 1 dòng code là Docker huỷ cache
  và cài lại toàn bộ thư viện.
- Không `USER` → container chạy bằng root; thoát được khỏi app là có quyền
  root trên host.
- Không `HEALTHCHECK` → Docker/orchestrator không biết container còn phục
  vụ được không.
- Cổng cố định `8000` → cloud (Railway, Render, Cloud Run) tự gán `$PORT`
  khác thì app không nghe đúng cổng.

### Code

```dockerfile
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local

COPY app ./app
COPY utils ./utils
COPY requirements.txt .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()" || exit 1

CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

### Giải thích từng phần

| Phần | Vì sao |
|---|---|
| `FROM python:3.11-slim AS builder` | Stage đầu được phép nặng — cài dependency, biên dịch nếu cần — rồi bị vứt đi hoàn toàn. Chỉ stage cuối trở thành image thật. |
| `COPY requirements.txt .` → `pip install --prefix=/install` → **sau đó** `COPY app ./app` | Docker cache theo layer, huỷ cache từ layer đầu tiên thay đổi. Copy source code sau `pip install` nghĩa là sửa code không bao giờ làm cache thư viện bị huỷ. |
| `FROM python:3.11-slim AS runtime` + `COPY --from=builder /install /usr/local` | Chỉ mang **kết quả** cài đặt sang stage cuối, không mang theo pip cache, build tool. Đây là lý do image tụt từ ~1GB xuống ~64MB content. |
| `RUN useradd --create-home --uid 10001 appuser` + `USER appuser` | Không chạy root. Một lỗ hổng nhỏ trong app (RCE, path traversal...) mà chạy root thì kẻ tấn công có quyền root trên host/container thay vì quyền hạn chế của `appuser`. |
| `HEALTHCHECK ... CMD python -c "urllib.request.urlopen('http://127.0.0.1:8000/health')"` | Gọi thẳng vào `/health` (liveness, không đụng Redis — xem CP1) mỗi 30s. Docker/orchestrator dựa vào exit code để biết có cần restart container không. |
| `CMD ["sh", "-c", "exec uvicorn ... --port ${PORT:-8000}"]` | Đọc `$PORT` từ môi trường, fallback `8000` khi chạy local. Railway/Render/Cloud Run tự gán `$PORT` — cố định `8000` sẽ làm health check trên cloud timeout. `exec` khiến `uvicorn` thay thế `sh` làm PID 1, để nhận trực tiếp SIGTERM — xem CP4. |
| `--host 0.0.0.0` | Bind `127.0.0.1` chỉ nghe được từ trong chính container; bên ngoài (host, load balancer) không gọi vào được. |

### Test tương ứng

```bash
pytest tests/test_cp2.py::TestDockerfile -v
```

- `test_multi_stage_build` — ≥2 lệnh `FROM`, có `AS <tên-stage>`
- `test_base_image_gon_nhe` — base image chứa `slim`/`alpine`
- `test_cai_dependency_truoc_khi_copy_source` — thứ tự `COPY requirements.txt` → `pip install` → `COPY` source
- `test_khong_chay_bang_root` — có `USER`, không phải `root`
- `test_co_healthcheck` — có `HEALTHCHECK`
- `test_khong_hardcode_secret` — không có `sk-`, `AGENT_API_KEY=`, `password` trong Dockerfile

---

## 2. `.dockerignore`

### Vấn đề

Thiếu `.dockerignore` (hoặc thiếu mục) nghĩa là `COPY . .` mang theo cả
`.env` (secret) và `.git` (lịch sử commit, có thể chứa secret cũ) vào image
— và image build xong bị đẩy lên registry công khai là secret bị lộ vĩnh
viễn.

### Code

```
.git
.gitignore
.env
.env.example
__pycache__
*.pyc
.venv
.pytest_cache
tests
screenshots
docs
*.md
```

### Giải thích

| Mục | Vì sao ignore |
|---|---|
| `.env`, `.env.example` | Secret thật (`.env`) và cả file mẫu — không thứ nào cần nằm trong image, secret luôn truyền lúc chạy container qua biến môi trường |
| `.git`, `.gitignore` | Lịch sử git không cần cho runtime, chỉ làm image phình to (có thể hàng chục/hàng trăm MB) |
| `__pycache__`, `*.pyc` | Bytecode cache, build lại trong container là đủ |
| `.venv`, `.pytest_cache` | Riêng máy dev, không liên quan runtime |
| `tests`, `docs`, `*.md`, `screenshots` | Tài liệu/test không cần chạy trong production; giữ image chỉ chứa thứ cần để serve request |

**Không ignore:** `app/`, `utils/`, `requirements.txt` — đây là những thứ
image **cần** để chạy; test `test_khong_loai_tru_nham_file_can_thiet` kiểm
tra chính xác điều này.

### Test tương ứng

```bash
pytest tests/test_cp2.py::TestDockerignore -v
```

- `test_ton_tai_va_day_du` — tồn tại, có đủ `.env`, `__pycache__`, `.git`, `.venv`
- `test_khong_loai_tru_nham_file_can_thiet` — không lỡ tay ignore `app`, `utils`, `requirements.txt`

---

## 3. `docker-compose.yml` — service `agent`

### Vấn đề

Compose ban đầu chỉ có `redis`. Cần thêm `agent` sao cho `docker compose up`
dựng được cả stack, và hai lỗi kinh điển cần tránh: viết thẳng secret vào
YAML, và dùng `localhost` để nối tới Redis (trong container, `localhost` là
chính container đó, không phải máy host hay container khác).

### Code

```yaml
agent:
  build: .
  ports:
    - "8000:8000"
  environment:
    AGENT_API_KEY: ${AGENT_API_KEY}
    REDIS_URL: redis://redis:6379/0
    RATE_LIMIT_PER_MINUTE: ${RATE_LIMIT_PER_MINUTE:-10}
    MONTHLY_BUDGET_USD: ${MONTHLY_BUDGET_USD:-10.0}
    LOG_LEVEL: ${LOG_LEVEL:-INFO}
  depends_on:
    - redis
  healthcheck:
    test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"]
    interval: 10s
    timeout: 5s
    retries: 5
```

### Giải thích từng phần

| Phần | Vì sao |
|---|---|
| `build: .` | Build từ `Dockerfile` ở gốc repo, không dùng image có sẵn |
| `ports: "8000:8000"` | Map cổng container ra host để `curl localhost:8000` từ máy dev gọi được |
| `AGENT_API_KEY: ${AGENT_API_KEY}` | Nội suy biến môi trường — compose tự đọc từ `.env` cùng thư mục. **Không** viết `AGENT_API_KEY: "khoa-thuc"` thẳng vào file này, vì file này thường được commit vào git |
| `REDIS_URL: redis://redis:6379/0` | `redis` là **tên service** trong compose network, dùng làm hostname. `localhost` ở đây sẽ trỏ vào chính container `agent`, không có Redis nào chạy trong đó → connection refused |
| `depends_on: [redis]` | Đảm bảo Docker khởi động `redis` trước `agent` (dù không đợi Redis "sẵn sàng" hoàn toàn — chỉ đợi container start) |
| `healthcheck` | Compose dùng để biết container `agent` đã lên chưa (health: starting → healthy), quan trọng khi có service khác cần chờ nó |

### Test tương ứng

```bash
pytest tests/test_cp2.py::TestDockerCompose -v
```

- `test_co_service_agent_va_redis` — cả hai service tồn tại
- `test_agent_build_tu_dockerfile` — có khóa `build`
- `test_agent_phu_thuoc_redis` — `depends_on` chứa `redis`
- `test_agent_tro_dung_toi_redis_service` — `REDIS_URL` bắt đầu bằng `redis://redis`, không phải `localhost`
- `test_secret_khong_nam_trong_compose` — `AGENT_API_KEY` là `${...}`, không hardcode
- `test_agent_co_healthcheck` — có khóa `healthcheck`

---

## 4. Bằng chứng chạy thật (không chỉ pytest)

### Build

```bash
docker build -t day12-agent:prod .
docker images day12-agent:prod
```

```
IMAGE               DISK USAGE   CONTENT SIZE
day12-agent:prod    270MB        63.7MB
```

Dưới ngưỡng 500MB đề bài yêu cầu — nhờ multi-stage (không mang compiler/pip
cache sang stage cuối) + base `slim`.

### Compose up — cả stack

```bash
docker compose up -d
docker compose ps
```

```
NAME       IMAGE                COMMAND                  STATUS                     PORTS
agent-1    ...-agent            "sh -c 'uvicorn app...'  Up (health: healthy)      0.0.0.0:8000->8000/tcp
redis-1    redis:7-alpine       "docker-entrypoint..."   Up (healthy)               0.0.0.0:6379->6379/tcp
```

### Health check qua container thật

```bash
curl -i http://localhost:8000/health
```

```
HTTP/1.1 200 OK
content-type: application/json

{"status":"ok","service":"day12-agent","version":"1.0.0"}
```

### Log JSON structured (CP1) hoạt động cả trong container

```
{"event": "service_started", "level": "info", "timestamp": "2026-08-10T03:19:51.574501+00:00", "service": "day12-agent", "version": "1.0.0"}
INFO:     127.0.0.1:49696 - "GET /health HTTP/1.1" 200 OK
```

### Sự cố gặp phải & cách xử lý

Lần chạy `docker compose up -d` đầu tiên báo lỗi:

```
Error response from daemon: failed to set up container networking:
failed to bind host port 0.0.0.0:8000/tcp: address already in use
```

**Nguyên nhân:** cổng 8000 đang bị chiếm bởi `uvicorn --reload` chạy tay từ
Checkpoint 1 (dev server song song với container). Container `agent` khi đó
vẫn được **tạo** (`Created`) nhưng không **start** được, và khi start lại
sau khi giải phóng cổng, compose tái sử dụng nhầm container cũ thiếu port
mapping.

**Cách xử lý:**
1. Dừng `uvicorn` tay (`Ctrl+C`) để giải phóng cổng 8000.
2. `docker compose up -d --force-recreate agent` — buộc tạo lại container
   với đúng cấu hình port từ `docker-compose.yml`.

Bài học: **không chạy song song** `uvicorn --reload` tay và `docker compose
up` cùng map một cổng — chọn một trong hai khi test.

---

## Chốt lại

| File | Thay đổi chính | Trạng thái |
|---|---|---|
| `Dockerfile` | Multi-stage, slim base, non-root, HEALTHCHECK, `$PORT` | ✅ build thật OK, 63.7MB |
| `.dockerignore` | Thêm `.env`, `.git`, `.venv`, `__pycache__`, `tests`, `docs`, ... | ✅ không leak secret, không loại nhầm file cần |
| `docker-compose.yml` | Thêm service `agent`: build, port, env qua `${...}`, `redis://redis`, depends_on, healthcheck | ✅ compose up thật, `/health` 200 qua container |

Checkpoint 2: **16/16 test pass** (bao gồm docker build + size thật) — sẵn
sàng sang Block 3 (API Security).
