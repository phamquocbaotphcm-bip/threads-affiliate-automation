"""90-Day Product & Post Bank Manager (3 posts/day x 90 days = 270 links)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

TARGET_BANK_SIZE = 270
DAILY_SLOTS = ("08:30", "12:30", "20:30")

_BRACKET_RE = re.compile(r"(\[[^\]]*\]|【[^】]*】|\([^\)]*\))")
_NON_TEXT_RE = re.compile(r"[^\w\s,.\-/&À-ỹà-ỹ]", re.UNICODE)

HOOK_TEMPLATES = (
    "Ở trọ mới thấy mấy món nhỏ nhỏ kiểu {label} cứu cánh cực kỳ.",
    "Ai hay lười dọn góc phòng giống mình thì ngó thử {label} này xem.",
    "Tầm {price_k} mà kiếm được {label} dùng ổn áp phết.",
    "Hồi mới dọn ra ở riêng cứ nghĩ không cần, giờ xài {label} mỗi ngày luôn.",
    "Sinh viên ở ghép phòng nhỏ rất nên có một cái {label} cho gọn.",
    "Bữa lướt thấy {label} giá {price_k} đặt đại về xài thử mà ưng ghê.",
    "Góc phòng trông bớt lộn xộn hẳn từ hôm mình thêm {label}.",
    "Không ngờ món đồ giá {price_k} như {label} lại giải quyết đúng chỗ ngứa.",
    "Mấy bạn hay thức khuya học bài chắc sẽ cần tới {label} này.",
    "Đợt này siết chi tiêu nên toàn săn đồ tầm {price_k}, như {label} thấy đáng tiền.",
    "Cứ tưởng mua về cho vui ai dè {label} thành món dùng nhiều nhất tuần.",
    "Nhỏ bạn qua phòng chơi hỏi hoài chỗ mua {label} này luôn.",
    "Phòng trọ chật thì cứ ưu tiên mấy món gọn nhẹ như {label} trước.",
    "Từ ngày có {label}, mấy việc lặt vặt buổi tối làm nhanh hơn hẳn.",
    "Tháng này tốn tiền nhất là mua mấy món tiện ích, nhưng riêng {label} thì không tiếc.",
    "Ai đang muốn nâng cấp góc bàn học mà ngân sách cỡ {price_k} thử ngó {label}.",
    "Đồ gia dụng giờ rẻ thật, tầm {price_k} đã có {label} dùng khá chắc chắn.",
    "Sáng nay dọn lại phòng mới nhớ ra {label} mua mấy tháng trước vẫn bền.",
    "Nhiều khi chỉ cần đổi một món nhỏ như {label} là sinh hoạt thoải mái hơn nhiều.",
    "Đi học về mệt mà thấy góc phòng gọn gàng nhờ {label} cũng đỡ stress.",
)

BODY_TEMPLATES = (
    "Mình đặt về dùng thử mấy hôm thấy khá ưng, giá chỉ khoảng {price_k} nên không bị đau ví. Gọn nhẹ, cất hay mang đi đều tiện.",
    "Xài cả tuần nay thấy ổn định, tầm {price_k} mà giải quyết gọn mấy việc lặt vặt trong phòng trọ. Đỡ phải loay hoay mỗi lần cần.",
    "Săn được deal tầm {price_k}, để góc bàn hay nhà tắm đều vừa vặn. Đồ bình dân nhưng giữ kỹ vẫn bền lắm.",
    "Cảm giác cầm nắm chắc tay hơn mình tưởng với mức giá {price_k}. Dùng hàng ngày tiết kiệm được khối thời gian.",
    "Lúc đầu hơi phân vân vì giá chỉ {price_k}, nhưng nhận hàng về dùng thật thấy đáng tiền hơn nhiều món đắt gấp đôi.",
    "Phù hợp nhất cho mấy bạn ở trọ một mình hoặc ký túc xá vì không chiếm diện tích. Chi phí {price_k} quá dễ chịu.",
    "Mình thích nhất là dễ vệ sinh và dùng được ngay, không phải lắp đặt rườm rà. Tầm {price_k} vậy là quá ổn.",
    "Góc phòng nhìn sạch sẽ hơn hẳn sau khi sắp xếp lại với món này. Giá {price_k} tính ra chưa bằng hai ly trà sữa.",
    "Dùng liên tục hai tuần rồi chưa thấy vấn đề gì, đúng kiểu ngon bổ rẻ cho sinh viên. Chỉ khoảng {price_k} thôi.",
    "Bạn nào hay quên hoặc bừa bộn giống mình thì món này đỡ cho nhiều lắm. Bỏ ra {price_k} thấy nhẹ đầu hẳn.",
    "Nhỏ gọn nên chuyển trọ mang theo cũng dễ, không lo cồng kềnh. Mức giá {price_k} mua không cần đắn đo.",
    "Đợt trước hay mua đại ngoài chợ đắt hơn mà nhanh hỏng, chuyển qua đặt loại này {price_k} thấy khác hẳn.",
    "Thiết kế đơn giản, dễ phối với đồ có sẵn trong phòng. Tầm {price_k} là hợp lý cho nhu cầu cơ bản.",
    "Tối về mệt chỉ muốn mọi thứ sẵn sàng trong tầm tay, món này đáp ứng đúng nhu cầu đó. Giá khoảng {price_k}.",
    "Mình đã mua thêm cái thứ hai để dùng dự phòng vì thấy tiện quá. Chi phí {price_k} quá nhẹ nhàng.",
    "Không quá cầu kỳ nhưng đúng công năng cần thiết mỗi ngày. Với {price_k} thì khó đòi hỏi gì hơn.",
    "Mỗi lần dọn phòng cuối tuần giờ nhanh hơn trước một nửa. Đầu tư {price_k} mà hiệu quả rõ rệt.",
    "Mấy món nhỏ vậy thôi chứ thiếu là thấy bất tiện liền. Tầm {price_k} ai cũng sắm được.",
    "Review thật là không phải hàng cao cấp gì đâu, nhưng với {price_k} thì dùng rất ổn áp.",
    "Hợp với túi tiền học sinh sinh viên mà vẫn đảm bảo dùng bền qua nhiều tháng. Chỉ cỡ {price_k}.",
)

QUESTION_TEMPLATES = (
    "Ở đây có bạn nào dùng loại này chưa, thấy ổn không?",
    "Mọi người hay ưu tiên đồ giá rẻ hay mua loại đắt dùng lâu dài?",
    "Phòng trọ mọi người món tiện ích nào dùng nhiều nhất vậy?",
    "Tầm giá dưới 100k bạn thấy món nào đáng mua nhất?",
    "Bạn hay mua đồ gia dụng ở chợ gần nhà hay đặt online?",
    "Góc phòng của bạn hiện tại có món nào tâm đắc nhất không?",
    "Có ai hay bị nghiện săn mấy món lặt vặt kiểu này giống mình không?",
    "Mỗi tháng bạn dành khoảng bao nhiêu cho mấy món đồ tiện ích nhỏ?",
    "Theo mọi người tiêu chí quan trọng nhất khi mua đồ phòng trọ là gì?",
    "Bạn thích đồ tối giản một màu hay màu sắc nổi bật cho vui mắt?",
    "Ở ghép với bạn cùng phòng mọi người có hay chia nhau mua đồ chung không?",
    "Món đồ nào bạn mua về xong thấy hối hận vì không mua sớm hơn?",
    "Cuối tuần này bạn có dự định dọn lại góc học tập hay phòng ngủ không?",
    "Bạn thường xem đánh giá mấy sao trước khi bấm đặt hàng?",
    "Khi chuyển trọ bạn thấy món đồ nào khó mang theo nhất?",
    "Ngoài món này ra mọi người còn gợi ý đồ gì hay cho phòng nhỏ không?",
    "Bạn thích săn mã giảm giá vào khung giờ nào trong ngày?",
    "Có ai hay đặt hàng lúc nửa đêm xong sáng ra quên mất mình đặt gì không?",
    "Nếu chấm điểm độ gọn gàng góc phòng hiện tại bạn cho mấy điểm?",
    "Món đồ đầu tiên bạn tự sắm khi ra ở riêng là gì thế?",
)

CTA_TEMPLATES = (
    "Link {label} mình để dưới đây cho ai cần nha: {affiliate_url}",
    "Chỗ mình đặt {label} uy tín giá ổn đây nhé: {affiliate_url}",
    "Bạn nào hỏi {label} thì xem chi tiết ở đây nha: {affiliate_url}",
    "Mình gắn sẵn đường dẫn {label} ở đây cho tiện tìm: {affiliate_url}",
    "Ai muốn tham khảo {label} giống mình thì vào đây xem nhé: {affiliate_url}",
    "Thông tin sản phẩm {label} mình để ngay đây nha: {affiliate_url}",
    "Để lại link {label} ở đây cho bạn nào đang tìm mua: {affiliate_url}",
    "Shop mình hay mua {label} giá mềm đây nhé: {affiliate_url}",
    "Xem giá hiện tại của {label} ở link này nha: {affiliate_url}",
    "Cần mua {label} thì bấm vào đây xem thử nhé: {affiliate_url}",
)


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


def clean_product_label(name: str) -> str:
    """Strip Shopee promotional tags, emojis, and ALL-CAPS spam from product names."""
    cleaned = _BRACKET_RE.sub(" ", str(name))
    cleaned = _NON_TEXT_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split()[:6]
    normalized: List[str] = []
    for word in words:
        if len(word) >= 2 and word.isupper():
            normalized.append(word.lower())
        else:
            normalized.append(word.lower())
    label = " ".join(normalized).strip()
    return label or "món đồ tiện ích"


def generate_natural_post(
    item: Dict[str, Any],
    index: int = 1,
    variant_offset: int = 0,
) -> Dict[str, Any]:
    """Generate diverse, natural Vietnamese Threads copy with zero hashtag spam."""
    label = clean_product_label(str(item.get("name", "món đồ tiện ích")))
    price = int(item.get("price_vnd", 0))
    price_k = f"{max(1, round(price / 1000))}k" if price > 0 else "giá mềm"

    h_idx = (index * 3 + variant_offset * 7) % len(HOOK_TEMPLATES)
    b_idx = (index * 5 + variant_offset * 11) % len(BODY_TEMPLATES)
    q_idx = (index * 7 + variant_offset * 13) % len(QUESTION_TEMPLATES)
    c_idx = (index + variant_offset) % len(CTA_TEMPLATES)

    return {
        "id": item.get("post_id") or f"BANK-{index:03d}",
        "hook": HOOK_TEMPLATES[h_idx].format(label=label, price_k=price_k),
        "body": BODY_TEMPLATES[b_idx].format(label=label, price_k=price_k),
        "engagement_question": QUESTION_TEMPLATES[q_idx],
        "affiliate_comment_cta": CTA_TEMPLATES[c_idx].replace(
            "{label}", label
        ),
        "hashtags": "",
        "topic_tag": "Đồ tiện ích",
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
            "image_url": str(raw.get("image_url", "")).strip(),
            "post": raw.get("post") or generate_natural_post(raw, index=next_idx),
        }
        bank.append(entry)
        seen_urls.add(url)
        added += 1

    save_bank(bank_path, bank)
    return added, len(bank)
