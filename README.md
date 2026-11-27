# Dự án Affiliate Threads `@hoinghiendotienich`

Hệ thống tự động hóa 24/7 cho kênh Threads `@hoinghiendotienich`, điều phối theo mô hình **Enterprise Orchestrator (A)** với 5 khối chuyên môn, tích hợp tự lấy/gia hạn OAuth token Threads, quản lý link Shopee Affiliate, kiểm định chất lượng độc lập (`Core_QA_Audit`) và cơ chế tự phát hiện/tự sửa lỗi ghi vào `logs/learn.log`.

## 1. Phân chia Đội ngũ & Quyền hạn (RBAC)

| Cấp | Role | Khối / Agent | Nhiệm vụ chính |
| :--- | :--- | :--- | :--- |
| **Cấp 0** | **Admin** | Chủ sở hữu | Phê duyệt `.env`, cấp token/link thật, duyệt bật `DRY_RUN=false` |
| **Cấp 1** | **Main Agent (A)** | `src/orchestrator.py` | Điều phối 24/7 theo 5 khung giờ, tổng hợp báo cáo, kích hoạt Circuit Breaker |
| **Cấp 2** | **Core_IT** | `src/auth_threads.py`, `src/self_heal.py` | OAuth 2.0 Threads, auto-refresh token, tự sửa lỗi & ghi `logs/learn.log` |
| **Cấp 2** | **Core_MKT** | `data/posts_seed.json` | 5 bài viết hook mạnh, nhấn mạnh nhu cầu giới trẻ, kích bình luận tăng CTR |
| **Cấp 2** | **Core_ECOM** | `src/shopee_affiliate.py`, `data/products.json` | Quản lý SKU tiện ích < 150k, validate/sinh link Shopee Affiliate |
| **Cấp 2** | **Core_QA_Audit** | `src/compliance_qa.py`, `tests/test_pipeline.py` | Cổng kiểm duyệt độc lập (độ dài <= 500 ký tự, cấm link trần, cấm từ khóa spam) |
| **Cấp 5** | **Satellite Agent** | Insights & Comment Collector | Thu thập lượt xem, click, bình luận/ý kiến người dùng, tính CTR |

## 2. Cấu hình môi trường (`.env`)

1. Sao chép `.env.example` thành `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Điền thông tin Meta Threads App & Shopee Affiliate (nếu dùng API):
   - `THREADS_APP_ID`, `THREADS_APP_SECRET`, `THREADS_REDIRECT_URI`
   - `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` (hoặc dùng `src/auth_threads.py` để lấy token qua OAuth flow)
   - `SHOPEE_APP_ID`, `SHOPEE_APP_SECRET` (tùy chọn — hoặc dán trực tiếp link rút gọn `https://s.shopee.vn/...` vào `data/products.json`)
3. Mặc định `DRY_RUN=true` để chạy thử nghiệm an toàn không đăng bài thật.

## 3. Chạy kiểm thử & Vận hành 24/7

- **Chạy Unit Tests:**
  ```powershell
  python -m unittest discover -s tests -v
  ```
- **Chạy thử nghiệm 1 chu kỳ (Dry-Run):**
  ```powershell
  python src/orchestrator.py --once --dry-run
  ```
- **Chạy tự động 24/7 (chỉ bật sau khi Admin điền `.env` và phê duyệt `DRY_RUN=false`):**
  ```powershell
  python src/orchestrator.py --daemon
  ```
