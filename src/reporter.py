"""Periodic Reporting & Growth Recommendation Engine (3-day, 14-day, 30-day)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.product_bank import DAILY_SLOTS, TARGET_BANK_SIZE, load_bank

PERIOD_LABELS = {
    "3d": "Báo cáo định kỳ 3 ngày",
    "14d": "Tổng kết 2 tuần",
    "30d": "Báo cáo tổng hợp tháng & Đề xuất phát triển",
}


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def build_report(
    period: str = "3d",
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, Any]:
    """Aggregate bank inventory, CTR insights, learn.log errors, and growth actions."""
    bank = load_bank(project_root / "data" / "product_bank_90d.json")
    state = _read_json(project_root / "logs" / "published_state.json", {})
    insights = _read_json(project_root / "logs" / "insights_report.json", {})
    learn_path = project_root / "logs" / "learn.log"

    published_urls = set(state.get("published_urls", []))
    total_bank = len(bank)
    remaining_links = sum(
        1 for item in bank if item.get("shopee_affiliate_url") not in published_urls
    )
    posts_per_day = len(DAILY_SLOTS)
    runway_days = round(remaining_links / posts_per_day, 1) if posts_per_day else 0.0

    results: List[Dict[str, Any]] = insights.get("results", [])
    ctrs = [
        float(r.get("insights", {}).get("ctr", 0.0))
        for r in results
        if "insights" in r
    ]
    avg_ctr = round(sum(ctrs) / len(ctrs), 4) if ctrs else 0.0
    target_ctr = float(insights.get("target_ctr_threshold", 0.035))

    learn_lines: List[str] = []
    if learn_path.exists():
        learn_lines = [
            line.strip()
            for line in learn_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    recommendations: List[str] = []
    if remaining_links < 30:
        recommendations.append(
            f"Cần bổ sung kho link qua Chrome (`browsermcp`): hiện còn {remaining_links} link chưa đăng "
            f"(đủ ~{runway_days} ngày, mục tiêu 90 ngày = {TARGET_BANK_SIZE} link)."
        )
    if avg_ctr < target_ctr:
        recommendations.append(
            f"CTR trung bình ({avg_ctr:.2%}) dưới ngưỡng {target_ctr:.2%}: "
            "nên A/B test hook mở đầu dạng nỗi đau phòng trọ/giá dưới 50k và chèn ảnh thực tế ở khung 20:30."
        )
    else:
        recommendations.append(
            f"CTR trung bình ({avg_ctr:.2%}) đạt/vượt ngưỡng {target_ctr:.2%}: "
            "giữ nhịp 3 bài/ngày (08:30, 12:30, 20:30) và nhân bản thêm SKU nhóm Hoa hồng Xtra (>=10%)."
        )

    if period in ("14d", "30d"):
        recommendations.append(
            "Bổ sung 20% bài không gắn link (dạng hỏi đáp/poll cộng đồng sinh viên) để đẩy phân phối tab Dành cho bạn."
        )
    if period == "30d":
        recommendations.append(
            "Đề xuất tháng tới: chọn Top 5 SKU có hoa hồng + lượt click cao nhất để làm series video ngắn/ảnh thật, "
            "đồng thời lọc bỏ các SKU hoa hồng <=2.5% nếu tỷ lệ chuyển đổi thấp."
        )

    now_vn = datetime.now(timezone(timedelta(hours=7)))
    date_str = now_vn.strftime("%Y-%m-%d")
    title = PERIOD_LABELS.get(period, f"Báo cáo ({period})")

    md_lines = [
        f"# {title} — @hoinghiendotienich ({date_str})",
        "",
        "## 1. Tình trạng kho link 90 ngày (3 bài/ngày)",
        f"- **Tổng link trong kho:** {total_bank} / {TARGET_BANK_SIZE}",
        f"- **Đã đăng:** {len(published_urls)} bài",
        f"- **Còn lại chưa đăng:** {remaining_links} link (đủ dùng khoảng **{runway_days} ngày**)",
        "",
        "## 2. Hiệu suất tương tác & CTR gần nhất",
        f"- **Số bài trong kỳ đo gần nhất:** {len(results)}",
        f"- **CTR trung bình:** {avg_ctr:.2%} (Mục tiêu: >= {target_ctr:.2%})",
        "",
        "## 3. Nhật ký tự sửa lỗi (`logs/learn.log`)",
        f"- **Tổng số bản ghi lỗi/học tập:** {len(learn_lines)}",
    ]
    for line in learn_lines[-5:]:
        md_lines.append(f"  - `{line}`")

    md_lines.extend(["", "## 4. Đề xuất phương án phát triển mới"])
    for idx, rec in enumerate(recommendations, start=1):
        md_lines.append(f"{idx}. {rec}")

    reports_dir = project_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"report_{period}_{date_str}.md"
    report_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return {
        "period": period,
        "report_path": str(report_path),
        "total_bank": total_bank,
        "remaining_links": remaining_links,
        "runway_days": runway_days,
        "avg_ctr": avg_ctr,
        "recommendations": recommendations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate periodic growth report")
    parser.add_argument(
        "--period",
        choices=("3d", "14d", "30d"),
        default="3d",
        help="Reporting window",
    )
    args = parser.parse_args()
    summary = build_report(period=args.period)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
