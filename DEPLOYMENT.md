# Báo Cáo Triển Khai Checkpoint 5

## 1. Thông Tin Học Viên

| Nội dung | Thông tin |
|---|---|
| Họ và tên | Nguyễn Mai Thanh Trúc |
| Mã học viên | 2A202601473 |
| Repository | https://github.com/trng28/K3-Day12-Lab-12-2A202601473 |

## 2. Thông Tin Dịch Vụ

| Nội dung | Thông tin |
|---|---|
| Tên dịch vụ | Academic Paper Research Agent |
| Nền tảng | Render |
| Public URL | https://k3-day12-lab-12-2a202601473.onrender.com |
| Phương thức triển khai | Docker |
| Nhánh triển khai | `main` |
| Ngày kiểm tra | 2026-08-10 |
| Health check | `/health` |
| Research API | `/api/chat/stream` |

Ứng dụng sử dụng React cho giao diện và FastAPI cho dịch vụ backend. Render
build image từ Dockerfile tại thư mục gốc của repository. Giao diện và API được
phục vụ trên cùng một domain.

## 3. Cấu Hình Môi Trường

Các giá trị bí mật được lưu trong Render Environment. Tài liệu này chỉ ghi tên
biến và nguồn cấu hình.

| Biến | Trạng thái | Nguồn cấu hình |
|---|---|---|
| `PORT` | Đã cấu hình | Render tự cấp |
| `AGENT_API_KEY` | Đã cấu hình | Render Environment |
| `REDIS_URL` | Đã cấu hình | Redis service của bài lab |
| `RATE_LIMIT_PER_MINUTE` | Đã cấu hình | Render Environment |
| `MONTHLY_BUDGET_USD` | Đã cấu hình | Render Environment |
| `LOG_LEVEL` | Đã cấu hình | Render Environment |
| `LLM_PROVIDER` | Đã cấu hình | Render Blueprint |
| `LLM_MODEL` | Đã cấu hình | Render Blueprint |
| `OPENAI_API_KEY` | Đã cấu hình | Render Environment |
| `SEMATIC_SCHOLAR_API` | Đã cấu hình | Render Environment |
| `ARXIV_USER_AGENT` | Đã cấu hình | Render Blueprint |

Biến `SEMATIC_SCHOLAR_API` được giữ để tương thích với cấu hình hiện tại. Ứng
dụng cũng hỗ trợ tên chuẩn `SEMANTIC_SCHOLAR_API_KEY`.

## Lệnh Kiểm Tra

Public URL: https://k3-day12-lab-12-2a202601473.onrender.com

```bash
curl -i https://k3-day12-lab-12-2a202601473.onrender.com/
curl -i https://k3-day12-lab-12-2a202601473.onrender.com/health
curl -i https://k3-day12-lab-12-2a202601473.onrender.com/ready
curl -i https://k3-day12-lab-12-2a202601473.onrender.com/api/health

curl -i -X POST https://k3-day12-lab-12-2a202601473.onrender.com/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'

curl -i -X POST https://k3-day12-lab-12-2a202601473.onrender.com/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "X-User-Id: sv-test" \
  -d '{"question":"Deploy là gì?"}'
```

Lệnh nghiệm thu Checkpoint 5:

```bash
LOCAL_FALLBACK=false pytest tests/test_cp5.py -v
```

## 5. Kết Quả Kiểm Tra Production

Kết quả được ghi nhận trực tiếp từ dịch vụ Render ngày 2026-08-10.

| Yêu cầu | Kết quả | Ghi chú |
|---|---|---|
| Giao diện tại `/` | HTTP 200 | React HTML được phục vụ thành công |
| Liveness tại `/health` | HTTP 200 | Dịch vụ `academic-paper-research-agent` hoạt động |
| Research health tại `/api/health` | HTTP 200 | arXiv và Semantic Scholar được khai báo |
| Cấu hình Semantic Scholar | Hợp lệ | API trả `semantic_scholar_api_key: true` |
| Readiness tại `/ready` | HTTP 404 | Source đã bổ sung endpoint, cần deploy commit mới |
| Xác thực tại `POST /ask` | HTTP 405 | Source đã bổ sung endpoint, cần deploy commit mới |

Không có giá trị API key nào xuất hiện trong response hoặc repository.

## 6. Kiểm Tra Trước Khi Deploy

Endpoint tương thích Checkpoint 5 đã được kiểm tra bằng FastAPI TestClient.

| Kiểm tra | Kết quả |
|---|---|
| `GET /ready` | HTTP 200 |
| `POST /ask` không có API key | HTTP 401 |
| `POST /ask` có API key hợp lệ | HTTP 200 |
| Bộ test research app | 13 test đạt |
| Kiểm tra nội dung tài liệu CP5 | 4 test đạt |

Các kết quả production tại `/ready` và `/ask` sẽ được cập nhật sau khi Render
hoàn tất deploy commit chứa endpoint tương thích.

## 7. Quy Trình CI/CD

Workflow `.github/workflows/ci-render.yml` chạy khi có push hoặc pull request
vào nhánh `main`.

1. Cài dependency và chạy test backend.
2. Build giao diện React.
3. Build Docker image production.
4. Chạy production gate sau khi các job kiểm tra hoàn tất.
5. Render triển khai commit khi GitHub checks đạt yêu cầu.

GitHub Environment `production` được liên kết với URL của dịch vụ Render. Các
secret production không được truyền vào CI. Render cung cấp secret cho container
khi dịch vụ khởi động.

## 8. Bằng Chứng

Ảnh `screenshots/health.png` ghi nhận trạng thái dịch vụ và kết quả health check.

## 9. Trạng Thái Hiện Tại

| Hạng mục | Trạng thái |
|---|---|
| HTTPS | Hoạt động |
| Giao diện React | Hoạt động |
| FastAPI | Hoạt động |
| arXiv | Hoạt động |
| Semantic Scholar | Đã nhận biến môi trường |
| Secret trong repository | Render Hook URL |
| Endpoint tương thích CP5 | Đã hoàn thiện trong source, chờ deploy |
