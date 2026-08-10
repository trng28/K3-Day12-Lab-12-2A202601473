## Mô tả bài toán

Mục tiêu của hệ thống là xây dựng một **Academic Research Agent** có khả năng tự động hóa quy trình nghiên cứu tài liệu học thuật. Thay vì người dùng phải tự tìm kiếm, đọc, tổng hợp và so sánh hàng chục bài báo, hệ thống sẽ sử dụng nhiều AI Agent chuyên biệt để hỗ trợ toàn bộ quy trình từ thu thập tài liệu, phân tích nội dung, kiểm chứng thông tin đến tạo báo cáo nghiên cứu.

## Workflow đề xuất

### 1. Planner

* Tiếp nhận câu hỏi hoặc chủ đề nghiên cứu.
* Phân rã thành các chủ đề nghiên cứu nhỏ hơn.
* Xây dựng kế hoạch và từ khóa tìm kiếm.

### 2. Search

* Tìm kiếm tài liệu học thuật từ **arXiv API** và **Semantic Scholar API**.
* Thu thập metadata, abstract, citation và reference của các bài báo.

### 3. Ranking

* Xếp hạng các bài báo theo mức độ liên quan và chất lượng.
* Chọn các bài báo quan trọng để phân tích chuyên sâu.

### 4. Reader

* Đọc và trích xuất thông tin từ các bài báo đã chọn.
* Chuẩn hóa các thông tin như:

  * Bài toán nghiên cứu
  * Phương pháp
  * Dataset
  * Chỉ số đánh giá
  * Kết quả thực nghiệm
  * Hạn chế
  * Đóng góp chính

### 5. Citation Graph

* Mở rộng phạm vi nghiên cứu thông qua các bài báo tham chiếu và các bài báo trích dẫn.
* Xác định các nghiên cứu nền tảng và các công trình liên quan.

### 6. Critic

* Kiểm tra tính nhất quán và độ tin cậy của thông tin.
* Phát hiện các kết quả mâu thuẫn hoặc so sánh không hợp lệ (ví dụ cùng Recall@10 nhưng trên các dataset khác nhau).
* Nếu bằng chứng chưa đủ, hệ thống sẽ quay lại bước tìm kiếm để bổ sung tài liệu.

### 7. Output

* Sinh báo cáo nghiên cứu cuối cùng bao gồm:

  * Tổng quan lĩnh vực
  * So sánh các phương pháp
  * Phân tích ưu, nhược điểm
  * Khoảng trống nghiên cứu
  * Đề xuất hướng tiếp cận
  * Danh sách tài liệu tham khảo

## Kết quả mong đợi

Workflow giúp **tự động hóa quy trình nghiên cứu tài liệu học thuật từ đầu đến cuối**, giảm đáng kể thời gian tìm kiếm và tổng hợp tài liệu, đồng thời đảm bảo các kết luận được xây dựng dựa trên bằng chứng và có khả năng truy vết nguồn tham khảo. Hệ thống hỗ trợ nhà nghiên cứu nhanh chóng nắm bắt bức tranh tổng quan của một lĩnh vực, xác định khoảng trống nghiên cứu và đề xuất hướng triển khai phù hợp.
