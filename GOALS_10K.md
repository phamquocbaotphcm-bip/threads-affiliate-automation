# MỤC TIÊU TĂNG TRƯỞNG: 10.000 FOLLOWERS TRONG 90 NGÀY (`@hoinghiendotienich`)

- **Ngày bắt đầu:** 2026-11-28
- **Thời hạn tối đa:** 90 ngày (đến 2026-02-26)
- **Mục tiêu cuối:** **10.000 Followers** trên Threads (`@hoinghiendotienich`)
- **Tốc độ trung bình cần đạt:** ~111 followers/ngày (tăng dần theo hiệu ứng đề xuất của thuật toán Threads)

## Lộ trình cột mốc (Milestones)

| Giai đoạn | Thời gian | Mục tiêu Followers | Tốc độ mục tiêu | Chiến lược trọng tâm |
| :--- | :--- | :--- | :--- | :--- |
| **Giai đoạn 1** | Ngày 1 – 14 | **500** | ~35/ngày | 3 bài Affiliate + 1 bài Viral Organic/ngày (`17:30`), trả lời 100% bình luận |
| **Giai đoạn 2** | Ngày 15 – 30 | **2.000** | ~100/ngày | A/B hook mở đầu theo dữ liệu CTR & views thật từ `growth_metrics.json` |
| **Giai đoạn 3** | Ngày 31 – 60 | **6.000** | ~135/ngày | Đẩy mạnh chủ đề thảo luận có reply rate cao sang tab *Dành cho bạn* |
| **Giai đoạn 4** | Ngày 61 – 90 | **10.000+** | ~150/ngày | Giữ ổn định 270 SKU không trùng + tối ưu khung giờ vàng |

## Hệ thống tự động hóa 24/7 trên Cloud GitHub Actions

1. **Đăng bài kiếm tiền (`threads_affiliate.yml`):** 3 bài/ngày (`08:30`, `12:30`, `20:30` GMT+7) từ kho 270 link.
2. **Động cơ tăng trưởng 10K (`growth_10k.yml`):**
   - `17:30` GMT+7: Đăng 1 bài **Viral Organic không gắn link** để kéo phân phối tự nhiên & follow.
   - `10:00`, `17:30`, `21:00` GMT+7: Tự động quét & trả lời bình luận người xem (`auto_reply_audience_comments`) + đo `followers_count` & `views` thật (`logs/growth_metrics.json`).
3. **Túc trực & Đăng bù (`watchdog_24_7.yml`):** Kiểm tra mỗi 4 tiếng (`15 */4 * * *`).
4. **Báo cáo tiến độ (`reporting.yml`):** Báo cáo 3 ngày / 2 tuần / 1 tháng kèm tốc độ thực tế hướng tới 10K.
