"""Independent Quality Assurance & Risk Control Gate (Core_QA_Audit)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

MAX_THREADS_CHARS = 500
MIN_NATURALNESS_SCORE = 85
MAX_SIMILARITY_RATIO = 0.45

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
HASHTAG_PATTERN = re.compile(r"(?<!\w)#\w+", re.UNICODE)
ALL_CAPS_SEQ_PATTERN = re.compile(r"\b[A-ZÀ-Ỹ]{3,}\b(?:\s+\b[A-ZÀ-Ỹ]{3,}\b){2,}")
TYPO_PUNCT_PATTERN = re.compile(r"(,,|(?<!\.)\.\.(?!\.)|\s+[,?!])")
UNFILLED_PLACEHOLDER_PATTERN = re.compile(r"\{[a-z_]+\}")
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
    naturalness_score: int = 100


def compose_main_post(post: Dict[str, Any]) -> str:
    """Format the main Threads post body without embedding raw affiliate links."""
    parts = [
        str(post.get("hook", "")).strip(),
        str(post.get("body", "")).strip(),
        str(post.get("engagement_question", "")).strip(),
        str(post.get("hashtags", "")).strip(),
    ]
    return "\n\n".join(p for p in parts if p)


def _word_bigrams(text: str) -> Set[Tuple[str, str]]:
    words = re.findall(r"\w+", text.lower(), re.UNICODE)
    if len(words) < 2:
        return set()
    return {(words[i], words[i + 1]) for i in range(len(words) - 1)}


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    grams_a = _word_bigrams(text_a)
    grams_b = _word_bigrams(text_b)
    if not grams_a or not grams_b:
        return 0.0
    union = grams_a | grams_b
    return len(grams_a & grams_b) / len(union)


def audit_post(
    post: Dict[str, Any],
    affiliate_url: str,
    recent_texts: Optional[Sequence[str]] = None,
) -> AuditResult:
    """Run strict pre-publish QA checks (naturalness >= 85, no spam, no duplicates)."""
    defects: List[str] = []
    score = 100
    post_id = str(post.get("id", "UNKNOWN"))
    main_text = compose_main_post(post)

    if len(main_text) < 40:
        defects.append(f"Main post too short ({len(main_text)} chars)")
        score -= 20

    if len(main_text) > MAX_THREADS_CHARS:
        defects.append(
            f"Main post exceeds {MAX_THREADS_CHARS} chars ({len(main_text)} chars)"
        )
        score -= 25

    if URL_PATTERN.search(main_text):
        defects.append(
            "Main post must not contain raw URLs; move link to affiliate_comment_cta"
        )
        score -= 30

    hashtags_found = HASHTAG_PATTERN.findall(main_text)
    if len(hashtags_found) >= 2:
        defects.append(
            f"Too many hashtags ({len(hashtags_found)}); keep 0 or at most 1 topic tag"
        )
        score -= 20

    if ALL_CAPS_SEQ_PATTERN.search(main_text):
        defects.append("Contains ALL-CAPS spam sequence; normalize product casing")
        score -= 20

    if TYPO_PUNCT_PATTERN.search(main_text):
        defects.append("Punctuation/spacing typo detected in post text")
        score -= 15

    if UNFILLED_PLACEHOLDER_PATTERN.search(main_text):
        defects.append("Unfilled template placeholder detected in main post")
        score -= 30

    lowered = main_text.lower()
    for kw in BANNED_KEYWORDS:
        if kw in lowered:
            defects.append(f"Contains banned/spam keyword: '{kw}'")
            score -= 30

    for cliche in AI_CLICHE_PATTERNS:
        if cliche in lowered:
            defects.append(f"Sounds like AI cliche: '{cliche}'")
            score -= 20

    if main_text.count("—") >= 2:
        defects.append("Overuses em-dash ('—'), rewrite in natural casual tone")
        score -= 15

    if recent_texts:
        for prev_text in recent_texts[-10:]:
            sim = _jaccard_similarity(main_text, prev_text)
            if sim >= MAX_SIMILARITY_RATIO:
                defects.append(
                    f"Too similar ({sim:.0%}) to a recent published post"
                )
                score -= 25
                break

    cta_template = str(post.get("affiliate_comment_cta", ""))
    if "{affiliate_url}" not in cta_template:
        defects.append("affiliate_comment_cta must include '{affiliate_url}' placeholder")
        score -= 30

    if not affiliate_url.startswith("https://"):
        defects.append("Affiliate URL must use HTTPS")
        score -= 30

    combined = f"{main_text}\n{cta_template}"
    if SECRET_PATTERN.search(combined):
        defects.append("Potential secret or token leak detected in post content")
        score -= 50

    final_score = max(0, score)
    verdict = (
        "PASS"
        if not defects and final_score >= MIN_NATURALNESS_SCORE
        else "REJECT"
    )
    return AuditResult(
        post_id=post_id,
        verdict=verdict,
        defects=defects,
        naturalness_score=final_score,
    )
