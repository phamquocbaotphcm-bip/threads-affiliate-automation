"""90-Day Product & Post Bank Manager (3 posts/day x 90 days = 270 links)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

TARGET_BANK_SIZE = 270
DAILY_SLOTS = ("08:30", "12:30", "20:30")


def load_bank(bank_path: Path) -> List[Dict[str, Any]]:
    """Load the 90-day product bank from JSON."""
    path = Path(bank_path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def save_bank(bank_path: Path, items: List[Dict[str, Any]]) -> None:
    """Persist the 90-day product bank to JSON."""
    path = Path(bank_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _short_product_label(name: str) -> str:
    cleaned = re.sub(r"\[[^\]]*\]", "", name).strip()
    words = cleaned.split()
    return " ".join(words[:7]) if len(words) > 7 else cleaned


def generate_natural_post(item: Dict[str, Any], index: int = 1) -> Dict[str, Any]:
    """Generate casual, human-sounding Vietnamese Threads copy for a product."""
    label = _short_product_label(str(item.get("name", "món đồ tiện ích")))
    price = int(item.get("price_vnd", 0))
    price_k = f"{max(1, round(price / 1000))}k" if price > 0 else "giá mềm"

    hooks = [
        f"Ở trọ mới thấy mấy món lặt vặt kiểu {label.lower()} cứu cánh cực kỳ.",
        f"Ai hay lười dọn góc phòng giống mình thì ngó thử {label.lower()} này xem.",
        f"Tầm {price_k} mà mua được {label.lower()} dùng ổn áp phết.",
    ]
    bodies = [
        f"Bữa mình đặt thử về dùng thấy tiện hơn hẳn, giá chỉ tầm {price_k} nên sinh viên mua không bị xót ví. Gọn nhẹ, dùng hàng ngày đỡ mất thời gian.",
        f"Mình xài cả tuần nay thấy khá ưng, tầm {price_k} mà giải quyết gọn mấy việc lặt vặt trong phòng trọ. Đỡ phải loay hoay mỗi lần cần.",
        f"Đợt này săn được deal tầm {price_k}, mang về để góc bàn hay phòng tắm đều vừa vặn. Đồ rẻ nhưng dùng kỹ vẫn bền lắm nha.",
    ]
    questions = [
        "Ở đây có bạn nào dùng loại này chưa, thấy ổn không?",
        "Mọi người hay ưu tiên đồ giá rẻ hay mua loại xịn dùng lâu dài?",
        "Phòng trọ mọi người món tiện ích nào dùng nhiều nhất vậy?",
    ]
    pick = index % 3
    return {
        "id": item.get("post_id") or f"BANK-{index:03d}",
        "hook": hooks[pick],
        "body": bodies[pick],
        "engagement_question": questions[pick],
        "affiliate_comment_cta": f"Link {label.lower()} mình để dưới đây cho ai cần nha: {{affiliate_url}}",
        "hashtags": "#hoinghiendotienich #tienich #phongtro #sinhvien",
    }


def add_products_to_bank(
    bank_path: Path,
    new_items: Iterable[Dict[str, Any]],
) -> Tuple[int, int]:
    """Append unique products (deduplicated by shopee_affiliate_url) to the bank."""
    bank = load_bank(bank_path)
    seen_urls = {str(item.get("shopee_affiliate_url", "")).strip() for item in bank}
    added = 0

    for raw in new_items:
        url = str(raw.get("shopee_affiliate_url", "")).strip()
        if not url or url in seen_urls:
            continue
        next_idx = len(bank) + 1
        entry: Dict[str, Any] = {
            "sku": raw.get("sku") or f"BANK-{next_idx:03d}",
            "name": str(raw.get("name", "")).strip(),
            "price_vnd": int(raw.get("price_vnd", 0)),
            "commission_rate": float(raw.get("commission_rate", 0.0)),
            "shopee_affiliate_url": url,
            "post": raw.get("post") or generate_natural_post(raw, index=next_idx),
        }
        bank.append(entry)
        seen_urls.add(url)
        added += 1

    save_bank(bank_path, bank)
    return added, len(bank)
