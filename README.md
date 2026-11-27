# Threads Affiliate Automation (High-CTR Interactive Pipeline)

Hệ thống tự động tạo nội dung tương tác trên **Threads** và gắn link **Affiliate** (Shopee, TikTok Shop, Lazada) được tối ưu chuyên sâu cho **CTR (Click-Through Rate)** và **0đ chi phí vận hành** (chạy hoàn toàn bằng Python chuẩn + GitHub Actions).

## Chiến lược tối ưu CTR trên Threads
1. **Bài chính (Main Post) — TUYỆT ĐỐI KHÔNG GẮN LINK:** Thuật toán Threads bóp reach các bài chứa link ngoài. Bài chính chỉ dùng Hook gây tò mò / tranh luận nhẹ / review thật để kéo comment & giữ chân người đọc.
2. **Bình luận 1 (Auto-Reply Link):** Tự động trả lời ngay dưới bài chính với lời kêu gọi mềm (Soft CTA) + link Affiliate có gắn tham số `utm_source=threads&utm_medium=auto_reply&utm_campaign=<product_id>_<hook_id>`.
3. **Bình luận 2 (Engagement Trigger):** Câu hỏi tương tác mồi giúp tăng tốc độ bình luận (thread velocity), đẩy bài lên đề xuất.
4. **Kiểm duyệt tự động (QA Compliance Gate):** Tự động chặn bài vượt 500 ký tự, chứa từ khóa spam/cấm, hoặc lỡ dính link ở bài chính.
5. **Đo lường & Xếp hạng CTR (SQLite Tracker):** Theo dõi CTR theo từng cặp `Hook × Product` để nhân bản các mẫu có CTR cao nhất.

## Cấu trúc thư mục
- `config/products.json`: Danh mục sản phẩm dễ bán, hoa hồng cao, dễ làm nội dung.
- `config/hooks.json`: Bộ khung Hook tương tác chuẩn CTR (`curiosity_gap`, `contrarian_take`, `budget_find`).
- `src/content_engine.py`: Bộ sinh chuỗi 3 bài tương tác + gắn UTM tự động.
- `src/compliance.py`: Cổng kiểm duyệt chất lượng & chống shadowban.
- `src/threads_client.py`: Kết nối chính thức Meta Threads Graph API (mặc định `dry_run=True` an toàn).
- `src/ctr_tracker.py`: Lưu lịch sử bài đăng và bảng xếp hạng CTR theo Hook.
- `src/pipeline.py`: Điểm chạy chính (CLI).
- `.github/workflows/auto_post.yml`: Tự động đăng bài 3 khung giờ vàng (08:00, 12:30, 20:30 GMT+7).

## Hướng dẫn chạy nhanh

### 1. Chạy thử tại máy (Dry-Run — An toàn, không đăng thật)
```bash
python3 -m unittest discover -s tests -v
python3 -m src.pipeline --mode publish
```

### 2. Kích hoạt đăng tự động lên Threads (Production)
1. Tạo ứng dụng tại [Meta for Developers](https://developers.facebook.com/) và bật quyền `threads_basic`, `threads_content_publish`.
2. Lấy `THREADS_USER_ID` và `THREADS_ACCESS_TOKEN` (Long-lived token).
3. Vào **GitHub Repo → Settings → Secrets and variables → Actions** và thêm 2 Secrets:
   - `THREADS_USER_ID`
   - `THREADS_ACCESS_TOKEN`
4. Cập nhật link Affiliate thật của bạn trong `config/products.json`.
5. Chạy thử từ tab **Actions → Threads Affiliate Auto-Post → Run workflow** (chọn `live: true` khi đã sẵn sàng).
