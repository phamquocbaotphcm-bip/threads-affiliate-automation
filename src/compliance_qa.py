"""Independent Quality Assurance & Risk Control Gate (Core_QA_Audit)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

MAX_THREADS_CHARS = 500
BANNED_KEYWORDS = (
    "cam kết 100%",
    "chữa dứt điểm",
    "giàu nhanh",
    "lừa đảo",
    "click ngay kẻo lỡ",
    "inbox nhận quà",
)
AI_CLICHE_PATTERNS = (
    "không thể phủ nhận",
    "tuyệt vời hơn nữa",
    "hãy cùng khám phá",
    "trong thế giới hiện đại",
    "chìa khóa vàng",
    "nâng tầm trải nghiệm",
    "đừng bỏ lỡ cơ hội",
    "sự lựa chọn hoàn hảo",
    "giải pháp tối ưu",
)
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
SECRET_PATTERN = re.compile(
    r"(THREADS_APP_SECRET|SHOPEE_APP_SECRET|EAA[A-Za-z0-9]{20,})",
    re.IGNORECASE,
)


@dataclass
class AuditResult:
    """Handoff verdict from Core_QA_Audit."""

    post_id: str
    verdict: str  # PASS | REJECT
    defects: List[str]


def compose_main_post(post: Dict[str, Any]) -> str:
    """Format the main Threads post body without embedding raw affiliate links."""
    parts = [
        post["hook"].strip(),
        post["body"].strip(),
        post["engagement_question"].strip(),
        post["hashtags"].strip(),
    ]
    return "\n\n".join(p for p in parts if p)


def audit_post(post: Dict[str, Any], affiliate_url: str) -> AuditResult:
    """Run Gate 1 & Gate 2 checks on a scheduled Threads post."""
    defects: List[str] = []
    post_id = str(post.get("id", "UNKNOWN"))
    main_text = compose_main_post(post)

    if len(main_text) > MAX_THREADS_CHARS:
        defects.append(
            f"Main post exceeds {MAX_THREADS_CHARS} chars ({len(main_text)} chars)"
        )

    if URL_PATTERN.search(main_text):
        defects.append(
            "Main post must not contain raw URLs; move link to affiliate_comment_cta"
        )

    lowered = main_text.lower()
    for kw in BANNED_KEYWORDS:
        if kw in lowered:
            defects.append(f"Contains banned/spam keyword: '{kw}'")

    for cliché in AI_CLICHE_PATTERNS:
        if cliché in lowered:
            defects.append(f"Sounds like AI cliché: '{cliché}'")

    if main_text.count("—") >= 2:
        defects.append("Overuses em-dash ('—'), rewrite in natural casual tone")

    cta_template = str(post.get("affiliate_comment_cta", ""))
    if "{affiliate_url}" not in cta_template:
        defects.append("affiliate_comment_cta must include '{affiliate_url}' placeholder")

    if not affiliate_url.startswith("https://"):
        defects.append("Affiliate URL must use HTTPS")

    combined = f"{main_text}\n{cta_template}"
    if SECRET_PATTERN.search(combined):
        defects.append("Potential secret or token leak detected in post content")

    verdict = "PASS" if not defects else "REJECT"
    return AuditResult(post_id=post_id, verdict=verdict, defects=defects)
