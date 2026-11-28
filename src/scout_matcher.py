"""Isolated peak-hour Threads scout matcher and reply deduplication."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.product_bank import load_bank  # noqa: E402

DEFAULT_SCOUT_STATE_PATH = PROJECT_ROOT / "logs" / "scout_replies_state.json"
DEFAULT_BANK_PATH = PROJECT_ROOT / "data" / "product_bank_90d.json"

BUYER_INTENT_PHRASES = (
    "xin link",
    "mua ở đâu",
    "rcm",
    "recommend",
    "gợi ý",
    "review",
    "hiệu gì",
    "loại nào",
    "chỗ mua",
    "bán ở đâu",
)

STOPWORDS: Set[str] = {
    "và", "là", "của", "cho", "với", "các", "những", "cái", "chiếc", "bộ",
    "món", "đồ", "dùng", "làm", "có", "không", "được", "này", "đó", "mình",
    "bạn", "mọi", "người", "ai", "xin", "link", "mua", "ở", "đâu", "review",
    "giá", "rẻ", "tốt", "nhất", "siêu", "cao", "cấp", "tiện", "ích", "đa",
    "năng", "phòng", "nhà", "màu", "hàng", "loại", "loại nào", "vừa", "để",
    "thì", "mà", "nha", "nhé", "ạ", "ơi", "vậy", "thấy", "cần", "tìm",
}

_TOKEN_RE = re.compile(r"[a-zà-ỹ0-9]{2,}", re.IGNORECASE)


def _meaningful_tokens(text: str) -> Set[str]:
    tokens = {m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")}
    return {t for t in tokens if t not in STOPWORDS}


def load_scout_state(state_path: Path = DEFAULT_SCOUT_STATE_PATH) -> Dict[str, Any]:
    """Load isolated peak-hour scout reply state."""
    path = Path(state_path)
    if not path.exists():
        return {"replied_urls": [], "daily_authors": {}, "history": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("replied_urls", [])
            data.setdefault("daily_authors", {})
            data.setdefault("history", [])
            return data
    except json.JSONDecodeError:
        pass
    return {"replied_urls": [], "daily_authors": {}, "history": []}


def save_scout_state(state_path: Path, state: Dict[str, Any]) -> None:
    """Persist isolated peak-hour scout reply state."""
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def has_buyer_intent(text: str) -> bool:
    """Return True if post text expresses genuine product/review/link intent."""
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in BUYER_INTENT_PHRASES)


def is_already_replied(
    state: Dict[str, Any],
    post_url: str,
    author: str = "",
    today_str: Optional[str] = None,
) -> bool:
    """Prevent duplicate replies to the same post or same author within one day."""
    clean_url = (post_url or "").split("?")[0].strip()
    if clean_url and clean_url in set(state.get("replied_urls", [])):
        return True
    clean_author = (author or "").lstrip("@").strip().lower()
    if clean_author:
        day = today_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        day_authors = {a.lower() for a in state.get("daily_authors", {}).get(day, [])}
        if clean_author in day_authors:
            return True
    return False


def match_product_from_bank(
    post_text: str,
    bank_path: Path = DEFAULT_BANK_PATH,
    min_overlap: int = 2,
) -> Optional[Dict[str, Any]]:
    """Find the best matching product in the 90-day bank by token overlap."""
    post_tokens = _meaningful_tokens(post_text)
    if not post_tokens:
        return None

    best_item: Optional[Dict[str, Any]] = None
    best_score = 0

    for item in load_bank(bank_path):
        url = str(item.get("shopee_affiliate_url", "")).strip()
        if not url.startswith("https://s.shopee.vn/"):
            continue
        name = str(item.get("name", ""))
        item_tokens = _meaningful_tokens(name)
        overlap = len(post_tokens & item_tokens)
        if overlap >= min_overlap and overlap > best_score:
            best_score = overlap
            best_item = item

    return best_item


def record_scout_reply(
    state_path: Path,
    post_url: str,
    author: str,
    sku: str,
    affiliate_url: str,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Record a posted peak-hour reply in the isolated state file."""
    ts = now_utc or datetime.now(timezone.utc)
    day = ts.strftime("%Y-%m-%d")
    clean_url = (post_url or "").split("?")[0].strip()
    clean_author = (author or "").lstrip("@").strip().lower()

    state = load_scout_state(state_path)
    if clean_url and clean_url not in state["replied_urls"]:
        state["replied_urls"].append(clean_url)

    day_list: List[str] = state["daily_authors"].setdefault(day, [])
    if clean_author and clean_author not in [a.lower() for a in day_list]:
        day_list.append(clean_author)

    state["history"].append(
        {
            "timestamp": ts.isoformat(),
            "date": day,
            "post_url": clean_url,
            "author": clean_author,
            "sku": sku,
            "shopee_affiliate_url": affiliate_url,
        }
    )
    save_scout_state(state_path, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Peak-hour Threads scout matcher")
    parser.add_argument("--match", type=str, help="Post text to match against bank")
    parser.add_argument("--check-url", type=str, help="Check if post URL was already replied")
    parser.add_argument("--author", type=str, default="", help="Post author handle")
    parser.add_argument(
        "--record",
        nargs=4,
        metavar=("URL", "AUTHOR", "SKU", "AFFILIATE_URL"),
        help="Record a completed peak-hour reply",
    )
    args = parser.parse_args()

    if args.check_url:
        state = load_scout_state(DEFAULT_SCOUT_STATE_PATH)
        replied = is_already_replied(state, args.check_url, args.author)
        print(json.dumps({"already_replied": replied}, ensure_ascii=False))
        return 0

    if args.match:
        intent = has_buyer_intent(args.match)
        matched = match_product_from_bank(args.match, DEFAULT_BANK_PATH) if intent else None
        print(
            json.dumps(
                {
                    "has_buyer_intent": intent,
                    "matched": {
                        "sku": matched.get("sku"),
                        "name": matched.get("name"),
                        "price_vnd": matched.get("price_vnd"),
                        "shopee_affiliate_url": matched.get("shopee_affiliate_url"),
                    }
                    if matched
                    else None,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.record:
        url, author, sku, aff_url = args.record
        record_scout_reply(DEFAULT_SCOUT_STATE_PATH, url, author, sku, aff_url)
        print(json.dumps({"recorded": True, "post_url": url}, ensure_ascii=False))
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
