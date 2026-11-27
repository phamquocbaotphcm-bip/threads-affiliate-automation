"""
Main Pipeline Orchestrator (Main Agent A)
End-to-end execution: Generate -> QA Compliance Gate -> Publish (Dry-Run/Live) -> Log CTR.
"""

import argparse
import json
import sys

from src.compliance import validate_thread_bundle
from src.content_engine import generate_thread_bundle
from src.ctr_tracker import CTRTracker
from src.threads_client import ThreadsClient


def run_pipeline(dry_run: bool = True) -> int:
    # Step 1: Core_MKT generates interactive thread bundle
    bundle = generate_thread_bundle()

    # Step 2: Core_QA_Audit validates compliance & CTR rules (Fail-Fast)
    passed, errors = validate_thread_bundle(bundle)
    if not passed:
        print("[Core_QA_Audit] REJECTED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    # Step 3: Core_IT publishes (or simulates in dry-run mode)
    client = ThreadsClient(dry_run=dry_run)
    result = client.publish_interactive_bundle(bundle)

    # Step 4: Log to CTR Tracker
    tracker = CTRTracker()
    row_id = tracker.log_post(bundle, result)

    output = {
        "status": "DONE",
        "dry_run": dry_run,
        "db_row_id": row_id,
        "product": bundle["product_name"],
        "hook_id": bundle["hook_id"],
        "publish_result": result,
        "preview": {
            "main_post": bundle["main_post"],
            "reply_link": bundle["reply_link"],
            "reply_engage": bundle["reply_engage"],
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


def print_report() -> int:
    tracker = CTRTracker()
    leaderboard = tracker.get_hook_ctr_leaderboard()
    print(json.dumps({"hook_ctr_leaderboard": leaderboard}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Automated Interactive Threads Affiliate Pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["publish", "report"],
        default="publish",
        help="Run mode: publish a new thread or print CTR leaderboard",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Publish live to Threads API (requires THREADS_USER_ID & THREADS_ACCESS_TOKEN)",
    )
    args = parser.parse_args()

    if args.mode == "report":
        return print_report()

    return run_pipeline(dry_run=not args.live)


if __name__ == "__main__":
    raise SystemExit(main())
