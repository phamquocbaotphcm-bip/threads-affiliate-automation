# Dự án Affiliate Threads `@hoinghiendotienich`

Hệ thống tự động hóa 24/7 cho kênh Threads `@hoinghiendotienich`, vận hành **3 bài/ngày × 90 ngày (mục tiêu 270 link sản phẩm)** trên **GitHub Actions** ngay cả khi tắt máy tính, kèm báo cáo định kỳ **3 ngày / 2 tuần / 1 tháng**.

## 1. Lịch vận hành & Kho 270 Link (`data/product_bank_90d.json`)

- **3 khung giờ vàng mỗi ngày (GMT+7):** `08:30`, `12:30`, `20:30`
- **Chống trùng lặp 90 ngày:** `logs/published_state.json` lưu danh sách `published_urls` và `slots_by_date` để mỗi sản phẩm chỉ đăng đúng 1 lần trong chu kỳ 90 ngày.
- **Nạp thêm link tự động qua Chrome (`browsermcp`):** Khi Admin mở máy tính, đăng nhập `https://affiliate.shopee.vn/offer/product_offer` và nhắn **"Nạp thêm link Shopee"**, Main Agent (A) sẽ tự động lấy link thật, sinh bài viết tự nhiên qua `src/product_bank.py` (không giống AI), kiểm định `Core_QA_Audit` và đẩy lên GitHub.

## 2. Báo cáo định kỳ & Đề xuất phát triển (`src/reporter.py`)

- **Mỗi 3 ngày (`--period 3d`):** Tình trạng kho link còn lại, CTR trung bình, nhật ký lỗi `logs/learn.log`.
- **Mỗi 2 tuần (`--period 14d`):** Tổng kết hiệu suất & điều chỉnh tỷ lệ bài tương tác tự nhiên.
- **Mỗi tháng (`--period 30d`):** Báo cáo tổng hợp & đề xuất phương án phát triển mới cho kênh.
- GitHub Actions workflow `.github/workflows/reporting.yml` tự động tạo file trong `reports/` và mở GitHub Issue thông báo cho Admin.

## 3. Kiểm thử & Chạy thủ công

- **Chạy Unit Tests:**
  ```powershell
  python -m unittest discover -s tests -v
  ```
- **Chạy thử nghiệm 1 chu kỳ (Dry-Run):**
  ```powershell
  python src/orchestrator.py --once --dry-run
  ```
- **Sinh báo cáo thủ công:**
  ```powershell
  python src/reporter.py --period 3d
  ```
