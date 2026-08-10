# Thông Tin Deploy - Checkpoint 5

Checkpoint này sử dụng phương án local fallback do môi trường hiện tại chưa có
phiên đăng nhập vào một nền tảng cloud. Giá trị bí mật chỉ nằm trong `.env` và
không được ghi vào tài liệu này.

## Thông Tin Học Viên

| Mục | Nội dung |
|-----|----------|
| Họ và tên | Nguyễn Mai Thành Trực |
| Mã học viên | 2A202601473 |
| Repo | https://github.com/trng28/K3-Day12-Lab-12-2A202601473 |

## Service

| Mục | Nội dung |
|-----|----------|
| Public URL | Không áp dụng - chạy tại `http://localhost:8000` |
| Platform | Railway (cấu hình sẵn), local fallback cho lần nghiệm thu này |
| Ngày nghiệm thu | 2026-08-10 |

## Biến Môi Trường

Ghi tên biến và **nguồn giá trị**, không ghi giá trị:

| Biến | Đã set | Ghi chú |
|------|--------|---------|
| `PORT` | Có | Docker Compose ánh xạ cổng 8000 |
| `AGENT_API_KEY` | Có | lấy từ `.env`, không nằm trong repo |
| `REDIS_URL` | Có | Redis service của Docker Compose |
| `RATE_LIMIT_PER_MINUTE` | Có | cấu hình qua môi trường |
| `MONTHLY_BUDGET_USD` | Có | cấu hình qua môi trường |
| `LOG_LEVEL` | Có | cấu hình qua môi trường |
| `LOCAL_FALLBACK` | Có | bật cho bộ test CP5 |

## Lệnh Kiểm Tra

Các lệnh đã chạy với URL local:

```bash
# 1. Liveness — mong đợi 200 {"status":"ok"}
curl -i http://localhost:8000/health

# 2. Readiness — mong đợi 200 {"status":"ready"} (đã nối được Redis)
curl -i http://localhost:8000/ready

# 3. Không có API key — mong đợi 401
curl -i -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'

# 4. Có API key — mong đợi 200 kèm câu trả lời
curl -i -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "X-User-Id: sv-test" \
  -d '{"question":"Deploy là gì?"}'

# 5. Rate limit — gọi 15 lần, những lần cuối phải trả 429
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code} " -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $AGENT_API_KEY" \
    -H "X-User-Id: sv-test" \
    -d '{"question":"test"}'
done; echo
```

## Kết Quả Chạy Thật

Kết quả nghiệm thu được ghi sau khi stack khởi động:

```text
GET /health                 -> 200, status=ok
GET /ready                  -> 200, status=ready, redis=true
POST /ask (không API key)   -> 401
```

## Ảnh Chụp Màn Hình

Ảnh kết quả kiểm tra được lưu tại `screenshots/health.png`.

---

## Lý Do Dùng Phương Án Dự Phòng

Môi trường thực hiện hiện không có phiên đăng nhập Railway/Render và không có
deployment cloud đã liên kết. Stack được nghiệm thu đầy đủ tại máy bằng Docker
Compose theo phương án dự phòng của lab guide.
