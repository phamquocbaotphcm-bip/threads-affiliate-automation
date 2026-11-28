"""Satellite Agent (Level 5): 24/7 Watchdog & Missed-Slot Auto-Recovery."""

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
from src.orchestrator import (
    THREADS_API_BASE,
    _load_published_state,
    _local_now,
    _threads_request,
    load_dotenv,
    run_cycle,
)
from src.product_bank import DAILY_SLOTS, load_bank
from src.self_heal import LearnLogger, RecoverableTaskError

LOW_BANK_THRESHOLD = 15


def check_token_health(
    auth: ThreadsAuthConfig,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Verify Threads OAuth token is active and matches THREADS_USER_ID."""
    if dry_run:
        return {"healthy": True, "username": "hoinghiendotienich", "mode": "dry_run"}

    if not auth.user_id or not auth.access_token:
        return {"healthy": False, "error": "Missing THREADS_USER_ID or THREADS_ACCESS_TOKEN"}

    qs = urllib.parse.urlencode(
        {"fields": "id,username", "access_token": auth.access_token}
    )
    try:
        data = _threads_request(f"{THREADS_API_BASE}/{auth.user_id}?{qs}")
        return {"healthy": True, "username": data.get("username", ""), "id": data.get("id", "")}
    except RecoverableTaskError as exc:
        return {"healthy": False, "error": str(exc)}


def find_missed_slots(
    state: Dict[str, Any],
    now_local: datetime,
    grace_minutes: int = 30,
) -> List[str]:
    """Return scheduled slots that passed grace_minutes ago and were not published today."""
    today_key = now_local.strftime("%Y-%m-%d")
    published_today = set(state.get("slots_by_date", {}).get(today_key, []))
    missed: List[str] = []
    for slot in DAILY_SLOTS:
        if slot in published_today:
            continue
        hour, minute = (int(part) for part in slot.split(":", 1))
        slot_dt = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now_local >= slot_dt + timedelta(minutes=grace_minutes):
            missed.append(slot)
    return missed


def run_watchdog(
    dry_run: bool = True,
    auto_recover: bool = True,
    now_local: Optional[datetime] = None,
    logs_dir: Optional[Path] = None,
    bank_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run one 24/7 Watchdog shift: check token, inventory, and recover missed slots."""
    load_dotenv(PROJECT_ROOT / ".env")
    active_logs_dir = Path(logs_dir) if logs_dir is not None else PROJECT_ROOT / "logs"
    active_logs_dir.mkdir(parents=True, exist_ok=True)
    active_bank_path = (
        Path(bank_path) if bank_path is not None else PROJECT_ROOT / "data" / "product_bank_90d.json"
    )
    learn_logger = LearnLogger(active_logs_dir)
    current_local = now_local or _local_now()
    auth = ThreadsAuthConfig.from_env()

    token_status = check_token_health(auth, dry_run=dry_run)
    bank = load_bank(active_bank_path)
    state = _load_published_state(active_logs_dir / "published_state.json")
    published_urls = set(state.get("published_urls", []))
    remaining_links = sum(
        1 for item in bank if item.get("shopee_affiliate_url") not in published_urls
    )
    missed_slots = find_missed_slots(state, current_local)

    alerts: List[str] = []
    recovered_posts = 0

    if not token_status.get("healthy"):
        err = token_status.get("error", "Unknown token error")
        alerts.append(f"TOKEN_UNHEALTHY: {err}")
        learn_logger.record(
            error_type="WATCHDOG_TOKEN_ALERT",
            context="24/7 Watchdog Shift",
            root_cause=err,
            auto_fix="Escalated to Admin via GitHub Issue alert",
            prevention_rule="Refresh or regenerate 60-day Threads token before expiry",
            resolved=False,
        )

    if remaining_links < LOW_BANK_THRESHOLD:
        alerts.append(
            f"LOW_BANK: Only {remaining_links} unpublished links left (< {LOW_BANK_THRESHOLD})"
        )

    if missed_slots and auto_recover and token_status.get("healthy") and remaining_links > 0:
        cycle_res = run_cycle(
            dry_run=dry_run,
            simulate_self_heal=False,
            respect_schedule=True,
            now_local=current_local,
            logs_dir=active_logs_dir,
        )
        recovered_posts = int(cycle_res.get("total_posts", 0))
        if recovered_posts > 0:
            learn_logger.record(
                error_type="MISSED_SLOT_RECOVERED",
                context=f"Watchdog recovered slots {missed_slots}",
                root_cause="Primary GitHub Actions cron was delayed or skipped",
                auto_fix=f"Auto-published {recovered_posts} due post(s) immediately",
                prevention_rule="Keep 4-hour Watchdog cron active as hot standby",
                resolved=True,
            )

    if alerts:
        status = "ALERT"
    elif recovered_posts > 0:
        status = "RECOVERED"
    else:
        status = "HEALTHY"

    summary = {
        "agent": "Satellite_Watchdog_24_7",
        "timestamp": current_local.isoformat(),
        "status": status,
        "dry_run": dry_run,
        "token_healthy": bool(token_status.get("healthy")),
        "remaining_links": remaining_links,
        "missed_slots_detected": missed_slots,
        "recovered_posts": recovered_posts,
        "alerts": alerts,
    }
    (active_logs_dir / "watchdog_status.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    env_dry_run = os.getenv("DRY_RUN", "true").strip().lower() == "true"

    parser = argparse.ArgumentParser(description="24/7 Satellite Watchdog for @hoinghiendotienich")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode_group.add_argument("--live", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=env_dry_run)
    args = parser.parse_args()

    res = run_watchdog(dry_run=args.dry_run, auto_recover=True)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if res["status"] == "ALERT":
        sys.exit(1)


if __name__ == "__main__":
    main()
