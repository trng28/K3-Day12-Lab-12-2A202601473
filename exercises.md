# Phiếu Phản Ánh — K3 Ngày 12

> **Bài làm cá nhân.** Trả lời bằng lời của chính bạn, dựa trên những gì bạn
> quan sát được khi chạy code — không sao chép đáp án của người khác.
>
> Cách trả lời: thay dòng `> *Câu trả lời của bạn*` bằng câu trả lời.
> `grade.py` đếm số câu đã trả lời (15 điểm cho 10 câu).
>
> Họ và tên: Nguyễn Mai Thành Trực  Mã học viên: 2A202601473

---

### Câu 1 — Fail fast (CP1)

Trong `Settings`, `agent_api_key` không có giá trị mặc định nên app chết ngay
khi khởi động nếu thiếu biến môi trường. Hãy mô tả một tình huống cụ thể mà
việc "chết sớm" này cứu bạn, so với việc để mặc định `"changeme"`.

> Khi deploy thiếu `AGENT_API_KEY`, ứng dụng dừng ngay trong giai đoạn khởi động và Render báo lỗi cấu hình. Nhờ đó tôi bổ sung secret trước khi nhận traffic, thay vì để khóa mặc định khiến endpoint công khai bị sử dụng trái phép.

---

### Câu 2 — Log cho máy đọc (CP1)

Chạy service và gọi `/ask` vài lần. Dán một dòng log JSON bạn thu được, rồi
nêu **hai** việc bạn làm được với dòng log đó mà `print("đã trả lời xong")`
không làm được.

> `{"event": "ask_completed", "level": "info", "timestamp": "2026-08-10T07:23:04.062923+00:00", "user_id": "sv01", "cost_usd": 0.0001}`. Log này cho phép lọc lỗi theo thời gian và người dùng, đồng thời tổng hợp chi phí theo ngày. Một câu `print` thông thường không cung cấp cấu trúc ổn định cho hai thao tác đó.

---

### Câu 3 — Kích thước image (CP2)

Build cả hai phiên bản và ghi lại số đo thật:

```bash
docker build -f <Dockerfile-1-stage> -t agent:single .
docker build -t agent:multi .
docker images | grep agent
```

| Bản | Dung lượng |
|-----|-----------|
| 1 stage (bản đầu) | Không còn image để đo lại |
| Multi-stage | 270 MB |

Giải thích: phần dung lượng chênh lệch đó là những gì?

> Image multi-stage hiện tại có dung lượng 270 MB. Phần chênh lệch thường đến từ compiler, header và cache cài đặt chỉ cần trong lúc build; các thành phần này không được sao chép sang runtime stage.

---

### Câu 4 — Thứ tự lệnh trong Dockerfile (CP2)

Sửa một ký tự trong `app/main.py` rồi build lại. Với Dockerfile của bạn, những
layer nào được dùng lại từ cache, layer nào phải chạy lại? Nếu bạn đặt
`COPY . .` lên trước `RUN pip install` thì kết quả khác thế nào?

> Khi chỉ sửa `app/main.py`, layer base image, `COPY requirements.txt` và `pip install` được dùng lại; layer copy source và các layer sau đó phải chạy lại. Nếu đặt `COPY . .` trước `pip install`, mọi thay đổi source đều làm mất cache dependency và kéo dài thời gian build.

---

### Câu 5 — Vì sao không chạy bằng root (CP2)

Container mặc định chạy bằng root. Mô tả chuỗi sự kiện dẫn từ "một lỗ hổng
trong code Python của bạn" tới "kẻ tấn công có quyền cao trên máy host", và
lệnh `USER` cắt đứt chuỗi đó ở chỗ nào.

> Nếu lỗ hổng cho phép thực thi lệnh trong container chạy root, kẻ tấn công có thể sửa filesystem, truy cập tài nguyên được mount hoặc khai thác cấu hình container để tiến gần host. `USER appuser` hạ quyền trước khi chạy ứng dụng, nên mã bị chiếm quyền chỉ có quyền của người dùng không đặc quyền.

---

### Câu 6 — Cửa sổ trượt (CP3)

Rate limit của bạn dùng sliding window 60 giây. Nếu thay bằng cách đếm theo
phút đồng hồ (reset lúc giây 00), một người dùng có thể gửi tối đa bao nhiêu
request trong 2 giây liên tiếp khi hạn mức là 10/phút? Giải thích cách đạt được
con số đó.

> Người dùng có thể gửi 20 request trong 2 giây: 10 request ở giây 59 của phút trước và 10 request ở giây 00 của phút sau. Sliding window vẫn nhìn thấy đủ 20 request trong 60 giây nên loại bỏ khe hở này.

---

### Câu 7 — Rate limit và cost guard (CP3)

Hai cơ chế này khác nhau ở điểm nào? Cho một tình huống mà rate limit cho qua
nhưng cost guard phải chặn, và một tình huống ngược lại.

> Rate limit kiểm soát tần suất, còn cost guard kiểm soát ngân sách tích lũy. Một request rất lớn vẫn nằm trong giới hạn 10 request/phút nhưng có thể vượt ngân sách và bị cost guard chặn. Ngược lại, người dùng còn nhiều ngân sách nhưng gửi quá nhanh sẽ bị rate limit chặn.

---

### Câu 8 — /health khác /ready (CP4)

Nếu gộp hai endpoint làm một và cho nó kiểm tra Redis, chuyện gì xảy ra với cụm
3 container khi Redis mất kết nối 30 giây? Trả lời theo đúng thứ tự sự kiện.

> Khi Redis mất kết nối, endpoint gộp trả 503 cho cả liveness. Orchestrator xem cả ba container là lỗi, lần lượt restart chúng, nhưng Redis vẫn chưa sẵn sàng nên các container tiếp tục thất bại. Tách `/health` và `/ready` giúp load balancer tạm ngừng gửi traffic mà không tạo vòng lặp restart.

---

### Câu 9 — Stateless (CP4)

Chạy `docker compose up --scale agent=3` rồi gọi `/ask` nhiều lần với cùng một
`X-User-Id`. Quan sát `history_length` trong response. Nếu lịch sử được lưu
trong một dict Python thay vì Redis, bạn sẽ thấy con số đó thay đổi thế nào?

> Với Redis, `history_length` tăng liên tục dù request được phân phối qua ba container. Nếu dùng dict Python, mỗi container có lịch sử riêng nên giá trị sẽ tăng không đều, lặp lại hoặc giảm khi request chuyển sang instance khác.

---

### Câu 10 — Deploy thật (CP5)

Ghi lại **một** lỗi bạn gặp khi deploy lên cloud (build fail, health check
timeout, sai REDIS_URL, app không đọc `$PORT`...): thông báo lỗi là gì, bạn
tìm ra nguyên nhân bằng cách nào, và sửa ra sao?

> Render deploy thành công nhưng URL gốc trả 404, trong khi `/health` vẫn trả `day12-agent`. Tôi kiểm tra từng endpoint và xác định service đang build Dockerfile Day12 cũ. Tôi sửa Dockerfile gốc để build React, chạy research FastAPI theo `$PORT`, phục vụ UI tại `/`, rồi clear build cache và deploy lại.
