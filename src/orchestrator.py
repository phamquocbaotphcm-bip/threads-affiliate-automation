"""Main Agent (A) 24/7 Orchestrator for @hoinghiendotienich Threads Affiliate."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.auth_threads import ThreadsAuthConfig, refresh_long_lived_token
from src.compliance_qa import audit_post, compose_main_post
from src.product_bank import DAILY_SLOTS, generate_natural_post, load_bank
from src.self_heal import LearnLogger, RecoverableTaskError, SelfHealingExecutor
from src.shopee_affiliate import (
    is_placeholder_url,
    is_valid_affiliate_url,
    load_products,
)

THREADS_API_BASE = "https://graph.threads.net/v1.0"


def load_dotenv(env_path: Path) -> None:
    """Load key=value pairs from .env without overriding existing env vars."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _threads_request(
    url: str,
    data: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Execute Threads Graph API HTTP request with error mapping for self-healing."""
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=encoded, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403) or (
            exc.code == 400 and ("OAuthException" in body or '"code":190' in body)
        ):
            raise RecoverableTaskError(
                "TOKEN_EXPIRED",
                f"Threads API auth error {exc.code}: {body}",
                root_cause=f"Access token expired or unauthorized: {body[:200]}",
            ) from exc
        if exc.code == 429:
            raise RecoverableTaskError(
                "RATE_LIMIT",
                f"Threads API rate limited (429): {body}",
                root_cause="Exceeded Threads API rate limit",
            ) from exc
        raise RecoverableTaskError(
            "NETWORK_ERROR",
            f"Threads API HTTP {exc.code}: {body}",
            root_cause=f"Upstream HTTP {exc.code}",
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RecoverableTaskError(
            "NETWORK_ERROR",
            f"Threads API network failure: {exc}",
            root_cause="Network timeout or DNS/connection error",
        ) from exc


def publish_threads_post(
    auth: ThreadsAuthConfig,
    text: str,
    reply_text: str,
    image_url: str = "",
    topic_tag: str = "",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Publish a Threads post (IMAGE with TEXT fallback) and attach affiliate reply."""
    use_image = bool(image_url and image_url.startswith("https://"))
    if dry_run:
        return {
            "media_id": f"dryrun_{abs(hash(text)) % 1000000}",
            "reply_id": f"dryrun_reply_{abs(hash(reply_text)) % 1000000}",
            "media_type": "IMAGE" if use_image else "TEXT",
            "status": "PUBLISHED_DRY_RUN",
        }

    if not auth.user_id or not auth.access_token:
        raise RecoverableTaskError(
            "TOKEN_EXPIRED",
            "Missing THREADS_USER_ID or THREADS_ACCESS_TOKEN",
            root_cause="Threads OAuth token is empty or expired",
        )

    create_url = f"{THREADS_API_BASE}/{auth.user_id}/threads"
    publish_url = f"{THREADS_API_BASE}/{auth.user_id}/threads_publish"

    base_payload: Dict[str, str] = {
        "text": text,
        "access_token": auth.access_token,
    }
    if topic_tag:
        base_payload["topic_tag"] = topic_tag

    media_type_used = "TEXT"
    container: Optional[Dict[str, Any]] = None
    if use_image:
        try:
            img_payload = dict(base_payload)
            img_payload["media_type"] = "IMAGE"
            img_payload["image_url"] = image_url
            container = _threads_request(create_url, data=img_payload)
            media_type_used = "IMAGE"
        except RecoverableTaskError as exc:
            if exc.error_type == "TOKEN_EXPIRED":
                raise
            container = None

    if container is None:
        txt_payload = dict(base_payload)
        txt_payload["media_type"] = "TEXT"
        container = _threads_request(create_url, data=txt_payload)
        media_type_used = "TEXT"

    published = _threads_request(
        publish_url,
        data={
            "creation_id": container["id"],
            "access_token": auth.access_token,
        },
    )
    reply_container = _threads_request(
        create_url,
        data={
            "media_type": "TEXT",
            "text": reply_text,
            "reply_to_id": published["id"],
            "access_token": auth.access_token,
        },
    )
    reply_published = _threads_request(
        publish_url,
        data={
            "creation_id": reply_container["id"],
            "access_token": auth.access_token,
        },
    )
    return {
        "media_id": published["id"],
        "reply_id": reply_published["id"],
        "media_type": media_type_used,
        "status": "PUBLISHED_LIVE",
    }


def collect_satellite_insights(
    post_id: str,
    auth: Optional[ThreadsAuthConfig] = None,
    media_id: str = "",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Satellite Agent: collect engagement metrics & audience feedback."""
    if dry_run:
        impressions = 1200
        clicks = 54
        return {
            "post_id": post_id,
            "impressions": impressions,
            "clicks": clicks,
            "ctr": round(clicks / impressions, 4),
            "top_comments": [
                "Giá học sinh sinh viên quá ổn, cho xin link với ạ",
                "Mình đang cần loại nhỏ gọn cho bàn học phòng trọ!",
            ],
        }

    if not auth or not auth.access_token or not media_id:
        return {
            "post_id": post_id,
            "impressions": 0,
            "clicks": 0,
            "ctr": 0.0,
            "top_comments": [],
        }

    try:
        insights_qs = urllib.parse.urlencode(
            {"metric": "views,likes,replies", "access_token": auth.access_token}
        )
        insights_data = _threads_request(
            f"{THREADS_API_BASE}/{media_id}/insights?{insights_qs}"
        )
        metrics = {
            item.get("name"): item.get("values", [{}])[0].get("value", 0)
            for item in insights_data.get("data", [])
        }
        views = int(metrics.get("views", 0))
        replies_count = int(metrics.get("replies", 0))

        replies_qs = urllib.parse.urlencode(
            {"fields": "text", "access_token": auth.access_token}
        )
        replies_data = _threads_request(
            f"{THREADS_API_BASE}/{media_id}/replies?{replies_qs}"
        )
        top_comments = [
            item.get("text", "")
            for item in replies_data.get("data", [])[:5]
            if item.get("text")
        ]
    except RecoverableTaskError:
        return {
            "post_id": post_id,
            "impressions": 0,
            "clicks": 0,
            "ctr": 0.0,
            "top_comments": [],
        }

    return {
        "post_id": post_id,
        "impressions": views,
        "clicks": replies_count,
        "ctr": round(replies_count / views, 4) if views > 0 else 0.0,
        "top_comments": top_comments,
    }


def _local_now() -> datetime:
    offset_hours = int(os.getenv("TIMEZONE_OFFSET_HOURS", "7"))
    return datetime.now(timezone(timedelta(hours=offset_hours)))


def _load_published_state(state_path: Path) -> Dict[str, Any]:
    default_state: Dict[str, Any] = {
        "published_urls": [],
        "slots_by_date": {},
        "recent_texts": [],
    }
    if not state_path.exists():
        return default_state
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_state
        data.setdefault("published_urls", [])
        data.setdefault("slots_by_date", {})
        data.setdefault("recent_texts", [])
        return data
    except json.JSONDecodeError:
        return default_state


def _is_slot_due(scheduled_slot: str, now_local: datetime) -> bool:
    hour, minute = (int(part) for part in scheduled_slot.split(":", 1))
    slot_dt = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return now_local >= slot_dt


def _load_candidate_queue(
    bank_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Load candidate items from 90-day bank, falling back to legacy seed files."""
    target_bank = (
        Path(bank_path)
        if bank_path is not None
        else PROJECT_ROOT / "data" / "product_bank_90d.json"
    )
    bank = load_bank(target_bank)
    if bank:
        queue: List[Dict[str, Any]] = []
        for idx, item in enumerate(bank):
            post = dict(item["post"])
            post["sku"] = item["sku"]
            post["affiliate_url"] = item["shopee_affiliate_url"]
            post["image_url"] = item.get("image_url", "")
            post["_raw_item"] = item
            post["_bank_index"] = idx + 1
            post.setdefault("scheduled_slot", DAILY_SLOTS[idx % len(DAILY_SLOTS)])
            queue.append(post)
        return queue

    products = load_products(PROJECT_ROOT / "data" / "products.json")
    posts: List[Dict[str, Any]] = json.loads(
        (PROJECT_ROOT / "data" / "posts_seed.json").read_text(encoding="utf-8")
    )
    for post in posts:
        post["affiliate_url"] = products[post["sku"]]["shopee_affiliate_url"]
        post["image_url"] = products[post["sku"]].get("image_url", "")
    return posts


def _audit_with_auto_rewrite(
    post: Dict[str, Any],
    affiliate_url: str,
    recent_texts: List[str],
) -> tuple[Dict[str, Any], Any]:
    """Audit post; if rejected, auto-rewrite with up to 2 alternative templates."""
    audit = audit_post(post, affiliate_url, recent_texts=recent_texts)
    if audit.verdict == "PASS":
        return post, audit

    raw_item = post.get("_raw_item")
    if not raw_item:
        return post, audit

    bank_idx = int(post.get("_bank_index", 1))
    for offset in (1, 2):
        rewritten = generate_natural_post(
            raw_item, index=bank_idx, variant_offset=offset
        )
        rewritten["sku"] = post.get("sku", "")
        rewritten["affiliate_url"] = affiliate_url
        rewritten["image_url"] = post.get("image_url", "")
        audit = audit_post(rewritten, affiliate_url, recent_texts=recent_texts)
        if audit.verdict == "PASS":
            return rewritten, audit
    return post, audit


def run_cycle(
    dry_run: bool = True,
    simulate_self_heal: bool = True,
    respect_schedule: bool = False,
    now_local: Optional[datetime] = None,
    logs_dir: Optional[Path] = None,
    bank_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute one orchestration cycle (3 posts/day across 08:30, 12:30, 20:30)."""
    load_dotenv(PROJECT_ROOT / ".env")
    active_logs_dir = Path(logs_dir) if logs_dir is not None else PROJECT_ROOT / "logs"
    active_logs_dir.mkdir(parents=True, exist_ok=True)
    learn_logger = LearnLogger(active_logs_dir)
    auth = ThreadsAuthConfig.from_env()
    current_local = now_local or _local_now()
    today_key = current_local.strftime("%Y-%m-%d")
    state_path = active_logs_dir / "published_state.json"
    state = _load_published_state(state_path)
    published_urls = set(state.get("published_urls", []))
    today_slots = set(state.get("slots_by_date", {}).get(today_key, []))
    recent_texts: List[str] = list(state.get("recent_texts", []))

    def _handle_token_refresh(_exc: RecoverableTaskError) -> None:
        refreshed = refresh_long_lived_token(auth.access_token, dry_run=dry_run)
        auth.access_token = refreshed["access_token"]

    executor = SelfHealingExecutor(
        learn_logger=learn_logger,
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        backoff_seconds=0.01 if dry_run else 2.0,
        fix_handlers={"TOKEN_EXPIRED": _handle_token_refresh},
    )

    if dry_run and simulate_self_heal:
        attempts = {"count": 0}

        def _transient_token_check() -> str:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RecoverableTaskError(
                    "TOKEN_EXPIRED",
                    "Simulated expired Threads token on pre-flight check",
                    root_cause="Access token TTL reached threshold",
                )
            return "TOKEN_OK"

        executor.run("preflight_token_check", _transient_token_check)

    candidates = _load_candidate_queue(bank_path=bank_path)
    target_ctr = float(os.getenv("TARGET_CTR_THRESHOLD", "0.035"))
    results: List[Dict[str, Any]] = []

    if respect_schedule:
        target_slots = [
            slot for slot in DAILY_SLOTS
            if slot not in today_slots and _is_slot_due(slot, current_local)
        ]
        pool = [
            item for item in candidates
            if item["affiliate_url"] not in published_urls
        ]
    else:
        target_slots = list(DAILY_SLOTS)
        pool = list(candidates)

    pool_idx = 0
    for slot in target_slots:
        published_for_slot = False
        while pool_idx < len(pool) and not published_for_slot:
            post = pool[pool_idx]
            pool_idx += 1
            post_id = post["id"]
            sku = post["sku"]
            affiliate_url = post["affiliate_url"]

            if not is_valid_affiliate_url(affiliate_url) or (
                not dry_run and is_placeholder_url(affiliate_url)
            ):
                raise RecoverableTaskError(
                    "INVALID_AFFILIATE_LINK",
                    f"Invalid or placeholder affiliate URL for {sku}",
                    root_cause="Affiliate URL failed domain/HTTPS/placeholder validation",
                )

            checked_post, audit = _audit_with_auto_rewrite(
                post, affiliate_url, recent_texts
            )
            if audit.verdict != "PASS":
                learn_logger.record(
                    error_type="COMPLIANCE_VIOLATION",
                    context=f"Core_QA_Audit rejected {post_id} after auto-rewrite",
                    root_cause="; ".join(audit.defects),
                    auto_fix="Skipped SKU and pulled next candidate in bank",
                    prevention_rule="Keep templates natural and unique vs last 10 posts",
                    resolved=True,
                )
                results.append(
                    {
                        "post_id": post_id,
                        "verdict": "REJECT",
                        "defects": audit.defects,
                        "naturalness_score": audit.naturalness_score,
                    }
                )
                continue

            main_text = compose_main_post(checked_post)
            reply_text = checked_post["affiliate_comment_cta"].format(
                affiliate_url=affiliate_url
            )
            slot_image = (
                checked_post.get("image_url", "") if slot == "20:30" else ""
            )
            topic_tag = str(checked_post.get("topic_tag", ""))
            pub_result = executor.run(
                f"publish_{post_id}",
                lambda mt=main_text, rt=reply_text, img=slot_image, tt=topic_tag: publish_threads_post(
                    auth, mt, rt, image_url=img, topic_tag=tt, dry_run=dry_run
                ),
            )
            recent_texts.append(main_text)
            recent_texts = recent_texts[-10:]
            if respect_schedule:
                published_urls.add(affiliate_url)
                today_slots.add(slot)
                state["published_urls"] = sorted(published_urls)
                state["slots_by_date"][today_key] = sorted(today_slots)
                state["recent_texts"] = recent_texts
                state_path.write_text(
                    json.dumps(state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            insights = collect_satellite_insights(
                post_id,
                auth=auth,
                media_id=pub_result.get("media_id", ""),
                dry_run=dry_run,
            )
            results.append(
                {
                    "post_id": post_id,
                    "slot": slot,
                    "sku": sku,
                    "verdict": audit.verdict,
                    "naturalness_score": audit.naturalness_score,
                    "publish": pub_result,
                    "insights": insights,
                    "ctr_above_target": insights["ctr"] >= target_ctr,
                }
            )
            published_for_slot = True

    report = {
        "channel": "@hoinghiendotienich",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "target_ctr_threshold": target_ctr,
        "total_posts": len(results),
        "results": results,
    }
    (active_logs_dir / "insights_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    env_dry_run = os.getenv("DRY_RUN", "true").strip().lower() == "true"

    parser = argparse.ArgumentParser(
        description="24/7 Orchestrator for @hoinghiendotienich Threads Affiliate"
    )
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--daemon", action="store_true", help="Run 24/7 loop")
    parser.add_argument(
        "--respect-schedule",
        action="store_true",
        help="Only publish posts whose scheduled_slot is due and not yet published today",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Simulate API calls without publishing",
    )
    mode_group.add_argument(
        "--live",
        dest="dry_run",
        action="store_false",
        help="Publish live to Threads Graph API",
    )
    parser.set_defaults(dry_run=env_dry_run)
    args = parser.parse_args()

    if args.daemon:
        while True:
            run_cycle(
                dry_run=args.dry_run,
                simulate_self_heal=False,
                respect_schedule=True,
            )
            time.sleep(60)
    else:
        report = run_cycle(
            dry_run=args.dry_run,
            simulate_self_heal=args.dry_run,
            respect_schedule=args.respect_schedule,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
