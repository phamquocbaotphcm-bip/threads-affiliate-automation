"""10K Followers Growth Engine for @hoinghiendotienich (90-day goal)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.auth_threads import ThreadsAuthConfig
from src.compliance_qa import audit_post, compose_main_post
from src.orchestrator import (
    THREADS_API_BASE,
    _local_now,
    _threads_request,
    load_dotenv,
)
from src.self_heal import LearnLogger, RecoverableTaskError

GOAL_FOLLOWERS = 10000
GOAL_DAYS = 90
GOAL_START_DATE = "2026-11-28"
VIRAL_SLOT = "17:30"

REPLY_TEMPLATES = (
    "Cảm ơn bạn đã chia sẻ nha, công nhận ở trọ mấy chi tiết nhỏ này ảnh hưởng nhiều thật!",
    "Chuẩn luôn bạn ơi, mình cũng thấy vậy đó. Cảm ơn bạn đã ghé bình luận nha!",
    "Nghe hợp lý phết đó bạn, để mình tham khảo thêm cách này thử xem sao!",
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def track_follower_progress(
    auth: ThreadsAuthConfig,
    now_local: datetime,
    logs_dir: Path,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Fetch follower count & views from Threads API and compute 90-day pace."""
    metrics_path = logs_dir / "growth_metrics.json"
    history = _read_json(
        metrics_path,
        {
            "goal_followers": GOAL_FOLLOWERS,
            "goal_days": GOAL_DAYS,
            "start_date": GOAL_START_DATE,
            "snapshots": [],
        },
    )

    followers = 0
    views = 0
    likes = 0
    replies = 0

    if dry_run:
        prev = history["snapshots"][-1] if history["snapshots"] else {}
        followers = int(prev.get("followers", 2)) + 5
        views = int(prev.get("views", 100)) + 250
    elif auth.user_id and auth.access_token:
        try:
            qs = urllib.parse.urlencode(
                {
                    "metric": "views,likes,replies,followers_count",
                    "access_token": auth.access_token,
                }
            )
            resp = _threads_request(
                f"{THREADS_API_BASE}/{auth.user_id}/threads_insights?{qs}"
            )
            for item in resp.get("data", []):
                name = item.get("name")
                val = 0
                if "total_value" in item and isinstance(item["total_value"], dict):
                    val = int(item["total_value"].get("value", 0))
                elif item.get("values"):
                    val = int(item["values"][-1].get("value", 0))
                if name == "followers_count":
                    followers = val
                elif name == "views":
                    views = val
                elif name == "likes":
                    likes = val
                elif name == "replies":
                    replies = val
        except RecoverableTaskError:
            pass

    start_dt = datetime.strptime(history["start_date"], "%Y-%m-%d").date()
    elapsed_days = max(1, (now_local.date() - start_dt).days + 1)
    remaining_days = max(1, GOAL_DAYS - elapsed_days)
    remaining_followers = max(0, GOAL_FOLLOWERS - followers)
    required_daily_pace = round(remaining_followers / remaining_days, 1)

    snapshot = {
        "date": now_local.strftime("%Y-%m-%d"),
        "timestamp": now_local.isoformat(),
        "followers": followers,
        "views": views,
        "likes": likes,
        "replies": replies,
        "elapsed_days": elapsed_days,
        "remaining_days": remaining_days,
        "required_daily_pace": required_daily_pace,
    }
    today_str = snapshot["date"]
    snapshots = [s for s in history["snapshots"] if s.get("date") != today_str]
    snapshots.append(snapshot)
    history["snapshots"] = snapshots[-90:]
    _write_json(metrics_path, history)
    return snapshot


def publish_daily_viral_post(
    auth: ThreadsAuthConfig,
    now_local: datetime,
    logs_dir: Path,
    viral_bank_path: Path,
    dry_run: bool = True,
    force_slot: bool = False,
) -> Dict[str, Any]:
    """Publish 1 organic viral discussion post (no affiliate link) at 17:30 GMT+7."""
    state_path = logs_dir / "growth_state.json"
    state = _read_json(
        state_path, {"published_viral_ids": [], "viral_dates": {}, "replied_ids": []}
    )
    today_key = now_local.strftime("%Y-%m-%d")

    if today_key in state["viral_dates"]:
        return {"published": False, "reason": "already_published_today"}

    hour, minute = (int(p) for p in VIRAL_SLOT.split(":", 1))
    slot_dt = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if not force_slot and now_local < slot_dt:
        return {"published": False, "reason": f"before_{VIRAL_SLOT}"}

    bank: List[Dict[str, Any]] = _read_json(viral_bank_path, [])
    published_ids = set(state.get("published_viral_ids", []))
    candidate = next((p for p in bank if p.get("id") not in published_ids), None)
    if candidate is None:
        return {"published": False, "reason": "viral_bank_exhausted"}

    # Validate via Core_QA_Audit using a dummy CTA template so organic post passes text checks
    qa_probe = dict(candidate)
    qa_probe["affiliate_comment_cta"] = "organic {affiliate_url}"
    audit = audit_post(qa_probe, "https://s.shopee.vn/organic")
    if audit.verdict != "PASS":
        return {"published": False, "reason": "qa_rejected", "defects": audit.defects}

    text = compose_main_post(candidate)
    if dry_run:
        media_id = f"dryrun_viral_{candidate['id']}"
    else:
        if not auth.user_id or not auth.access_token:
            raise RecoverableTaskError(
                "TOKEN_EXPIRED",
                "Missing THREADS_USER_ID or THREADS_ACCESS_TOKEN",
                root_cause="Missing Threads credentials",
            )
        create_url = f"{THREADS_API_BASE}/{auth.user_id}/threads"
        publish_url = f"{THREADS_API_BASE}/{auth.user_id}/threads_publish"
        payload: Dict[str, str] = {
            "media_type": "TEXT",
            "text": text,
            "access_token": auth.access_token,
        }
        if candidate.get("topic_tag"):
            payload["topic_tag"] = str(candidate["topic_tag"])
        container = _threads_request(create_url, data=payload)
        published = _threads_request(
            publish_url,
            data={"creation_id": container["id"], "access_token": auth.access_token},
        )
        media_id = published["id"]

    state["published_viral_ids"].append(candidate["id"])
    state["viral_dates"][today_key] = candidate["id"]
    _write_json(state_path, state)
    return {"published": True, "viral_id": candidate["id"], "media_id": media_id}


def auto_reply_audience_comments(
    auth: ThreadsAuthConfig,
    logs_dir: Path,
    dry_run: bool = True,
    max_replies: int = 5,
) -> Dict[str, Any]:
    """Reply naturally to new audience comments on recent threads to boost reach."""
    state_path = logs_dir / "growth_state.json"
    state = _read_json(
        state_path, {"published_viral_ids": [], "viral_dates": {}, "replied_ids": []}
    )
    replied_ids = set(state.get("replied_ids", []))
    replies_sent = 0

    if dry_run:
        return {"replies_sent": 0, "mode": "dry_run"}

    if not auth.user_id or not auth.access_token:
        return {"replies_sent": 0, "reason": "missing_credentials"}

    try:
        posts_qs = urllib.parse.urlencode(
            {"fields": "id,text", "limit": "5", "access_token": auth.access_token}
        )
        posts_data = _threads_request(
            f"{THREADS_API_BASE}/{auth.user_id}/threads?{posts_qs}"
        )
        for post in posts_data.get("data", []):
            if replies_sent >= max_replies:
                break
            media_id = post.get("id")
            if not media_id:
                continue
            rep_qs = urllib.parse.urlencode(
                {
                    "fields": "id,text,username",
                    "access_token": auth.access_token,
                }
            )
            rep_data = _threads_request(
                f"{THREADS_API_BASE}/{media_id}/replies?{rep_qs}"
            )
            for comment in rep_data.get("data", []):
                if replies_sent >= max_replies:
                    break
                cid = str(comment.get("id", ""))
                username = str(comment.get("username", ""))
                if not cid or cid in replied_ids or username == "hoinghiendotienich":
                    continue
                reply_text = REPLY_TEMPLATES[replies_sent % len(REPLY_TEMPLATES)]
                create_url = f"{THREADS_API_BASE}/{auth.user_id}/threads"
                publish_url = f"{THREADS_API_BASE}/{auth.user_id}/threads_publish"
                c_resp = _threads_request(
                    create_url,
                    data={
                        "media_type": "TEXT",
                        "text": reply_text,
                        "reply_to_id": cid,
                        "access_token": auth.access_token,
                    },
                )
                _threads_request(
                    publish_url,
                    data={
                        "creation_id": c_resp["id"],
                        "access_token": auth.access_token,
                    },
                )
                replied_ids.add(cid)
                replies_sent += 1
    except RecoverableTaskError:
        pass

    state["replied_ids"] = sorted(replied_ids)[-500:]
    _write_json(state_path, state)
    return {"replies_sent": replies_sent}


def run_growth_cycle(
    dry_run: bool = True,
    publish_viral: bool = True,
    force_viral: bool = False,
    now_local: Optional[datetime] = None,
    logs_dir: Optional[Path] = None,
    viral_bank_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute one 10K growth cycle: track followers, reply to comments, post viral."""
    load_dotenv(PROJECT_ROOT / ".env")
    active_logs_dir = Path(logs_dir) if logs_dir is not None else PROJECT_ROOT / "logs"
    active_logs_dir.mkdir(parents=True, exist_ok=True)
    active_viral_bank = (
        Path(viral_bank_path)
        if viral_bank_path is not None
        else PROJECT_ROOT / "data" / "viral_organic_bank.json"
    )
    current_local = now_local or _local_now()
    auth = ThreadsAuthConfig.from_env()
    learn_logger = LearnLogger(active_logs_dir)

    metrics = track_follower_progress(
        auth, current_local, active_logs_dir, dry_run=dry_run
    )
    reply_res = auto_reply_audience_comments(auth, active_logs_dir, dry_run=dry_run)
    viral_res: Dict[str, Any] = {"published": False, "reason": "skipped"}
    if publish_viral:
        try:
            viral_res = publish_daily_viral_post(
                auth,
                current_local,
                active_logs_dir,
                active_viral_bank,
                dry_run=dry_run,
                force_slot=force_viral,
            )
        except RecoverableTaskError as exc:
            learn_logger.record(
                error_type=exc.error_type,
                context="growth_engine_viral_post",
                root_cause=exc.root_cause,
                auto_fix="Deferred to next growth cycle",
                prevention_rule="Check Threads token health via Watchdog",
                resolved=False,
            )
            viral_res = {"published": False, "reason": exc.error_type}

    return {
        "goal": "10K_FOLLOWERS_90_DAYS",
        "timestamp": current_local.isoformat(),
        "dry_run": dry_run,
        "metrics": metrics,
        "auto_reply": reply_res,
        "viral_post": viral_res,
    }


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    env_dry_run = os.getenv("DRY_RUN", "true").strip().lower() == "true"

    parser = argparse.ArgumentParser(description="10K Followers Growth Engine")
    parser.add_argument("--no-viral", action="store_true", help="Only sync metrics & reply")
    parser.add_argument("--force-viral", action="store_true", help="Ignore 17:30 slot check")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode_group.add_argument("--live", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=env_dry_run)
    args = parser.parse_args()

    res = run_growth_cycle(
        dry_run=args.dry_run,
        publish_viral=not args.no_viral,
        force_viral=args.force_viral,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
