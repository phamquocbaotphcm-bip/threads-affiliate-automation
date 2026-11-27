"""
Compliance & QA Gate (Core_QA_Audit)
Validates Threads posts before publishing to protect organic reach and avoid shadowbans.
"""

import re
from typing import Dict, List, Tuple

MAX_THREADS_CHARS = 500
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

BANNED_KEYWORDS = [
    "cam kết 100%",
    "chữa dứt điểm",
    "kiếm tiền dễ dàng",
    "làm giàu không khó",
    "click ngay kẻo lỡ",
    "inbox nhận quà",
]


def validate_thread_bundle(bundle: Dict) -> Tuple[bool, List[str]]:
    """
    Validate a generated Threads post bundle:
    - Main post MUST NOT contain external URLs (prevents Threads reach suppression).
    - Reply 1 MUST contain a valid tracked URL.
    - Every post must be <= 500 characters.
    - No banned/spam keywords.
    """
    errors: List[str] = []

    main_post = bundle.get("main_post", "")
    reply_link = bundle.get("reply_link", "")
    reply_engage = bundle.get("reply_engage", "")

    if not main_post.strip():
        errors.append("main_post is empty")

    if len(main_post) > MAX_THREADS_CHARS:
        errors.append(f"main_post exceeds {MAX_THREADS_CHARS} chars ({len(main_post)})")

    if URL_PATTERN.search(main_post):
        errors.append("main_post contains a URL (violates CTR/reach rule: links belong in reply_link only)")

    if not URL_PATTERN.search(reply_link):
        errors.append("reply_link does not contain a valid URL")

    if "utm_source=threads" not in reply_link:
        errors.append("reply_link URL is missing UTM tracking parameters")

    if len(reply_link) > MAX_THREADS_CHARS:
        errors.append(f"reply_link exceeds {MAX_THREADS_CHARS} chars ({len(reply_link)})")

    if reply_engage and len(reply_engage) > MAX_THREADS_CHARS:
        errors.append(f"reply_engage exceeds {MAX_THREADS_CHARS} chars ({len(reply_engage)})")

    combined_lower = f"{main_post}\n{reply_link}\n{reply_engage}".lower()
    for kw in BANNED_KEYWORDS:
        if kw in combined_lower:
            errors.append(f"contains banned/spam keyword: '{kw}'")

    return (len(errors) == 0, errors)
