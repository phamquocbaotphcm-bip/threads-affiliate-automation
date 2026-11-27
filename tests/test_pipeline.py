"""Unit tests for @hoinghiendotienich Threads Affiliate pipeline (Core_QA_Audit)."""

from __future__ import annotations

import json
import tempfile
import typing
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src import shopee_affiliate
from src.auth_threads import ThreadsAuthConfig, build_authorization_url
from src.compliance_qa import audit_post
from src.orchestrator import PROJECT_ROOT, run_cycle
from src.product_bank import add_products_to_bank, load_bank
from src.reporter import build_report
from src.self_heal import (
    CircuitBreakerOpenError,
    LearnLogger,
    RecoverableTaskError,
    SelfHealingExecutor,
)
from src.shopee_affiliate import is_valid_affiliate_url, load_products


class TestPipeline(unittest.TestCase):
    def test_compliance_qa_pass_and_reject(self) -> None:
        valid_post = {
            "id": "TEST-01",
            "hook": "Đèn ngủ cảm biến giá rẻ cho phòng trọ.",
            "body": "Sạc USB dùng cả tháng, ánh sáng dịu không chói mắt.",
            "engagement_question": "Bạn thích đèn ánh sáng vàng hay trắng?",
            "affiliate_comment_cta": "Xem ở đây nha: {affiliate_url}",
            "hashtags": "#hoinghiendotienich",
        }
        res_pass = audit_post(valid_post, "https://s.shopee.vn/test123")
        self.assertEqual(res_pass.verdict, "PASS")
        self.assertEqual(res_pass.defects, [])

        bad_post = dict(valid_post)
        bad_post["body"] = "Cam kết 100% siêu rẻ tại https://s.shopee.vn/inline"
        res_reject = audit_post(bad_post, "https://s.shopee.vn/test123")
        self.assertEqual(res_reject.verdict, "REJECT")
        self.assertGreaterEqual(len(res_reject.defects), 2)

        ai_post = dict(valid_post)
        ai_post["body"] = "Không thể phủ nhận đây là sự lựa chọn hoàn hảo cho bạn."
        res_ai = audit_post(ai_post, "https://s.shopee.vn/test123")
        self.assertEqual(res_ai.verdict, "REJECT")

    def test_self_heal_retry_and_circuit_breaker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp)
            logger = LearnLogger(logs_dir)
            executor = SelfHealingExecutor(logger, max_retries=3, backoff_seconds=0.0)

            state = {"n": 0}

            def flaky_ok() -> str:
                state["n"] += 1
                if state["n"] < 2:
                    raise RecoverableTaskError("RATE_LIMIT", "429 Too Many Requests")
                return "OK"

            self.assertEqual(executor.run("flaky_ok", flaky_ok), "OK")
            kb = json.loads((logs_dir / "learn_kb.json").read_text(encoding="utf-8"))
            self.assertEqual([e["resolved"] for e in kb], [False, True])

            def always_fail() -> str:
                raise RecoverableTaskError("NETWORK_ERROR", "Connection reset")

            with self.assertRaises(CircuitBreakerOpenError):
                executor.run("always_fail", always_fail)

    def test_shopee_catalog_type_hints_and_oauth_url(self) -> None:
        typing.get_type_hints(shopee_affiliate.build_shopee_auth_header)
        typing.get_type_hints(shopee_affiliate.generate_short_link)

        products = load_products(PROJECT_ROOT / "data" / "products.json")
        self.assertEqual(len(products), 5)
        for sku, prod in products.items():
            self.assertTrue(
                is_valid_affiliate_url(prod["shopee_affiliate_url"]),
                msg=f"Invalid URL for {sku}",
            )

        cfg = ThreadsAuthConfig(
            app_id="123456",
            app_secret="secret",
            redirect_uri="https://localhost/callback",
            user_id="999",
            access_token="tok",
        )
        url = build_authorization_url(cfg)
        self.assertIn("client_id=123456", url)
        self.assertIn("threads_content_publish", url)

    def test_live_mode_rejects_placeholder_links(self) -> None:
        self.assertTrue(
            shopee_affiliate.is_placeholder_url("https://s.shopee.vn/REPLACE_WITH_YOUR_LINK_01")
        )
        self.assertFalse(
            shopee_affiliate.is_placeholder_url("https://s.shopee.vn/qlOgbpP6m")
        )

    def test_schedule_deduplication_and_dry_run_end_to_end(self) -> None:
        state_file = PROJECT_ROOT / "logs" / "published_state.json"
        if state_file.exists():
            state_file.unlink()

        midday = datetime(2026, 11, 27, 12, 30, tzinfo=timezone(timedelta(hours=7)))
        first = run_cycle(
            dry_run=True,
            simulate_self_heal=False,
            respect_schedule=True,
            now_local=midday,
        )
        self.assertEqual(first["total_posts"], 2)  # 08:30 & 12:30 only

        second = run_cycle(
            dry_run=True,
            simulate_self_heal=False,
            respect_schedule=True,
            now_local=midday,
        )
        self.assertEqual(second["total_posts"], 0)  # no duplicate publish

        full = run_cycle(dry_run=True, simulate_self_heal=True)
        self.assertEqual(full["total_posts"], 3)  # 3 posts/day cadence
        for item in full["results"]:
            self.assertEqual(item["verdict"], "PASS")
            self.assertTrue(item["ctr_above_target"])
        self.assertTrue((PROJECT_ROOT / "logs" / "learn.log").exists())
        self.assertTrue((PROJECT_ROOT / "logs" / "insights_report.json").exists())

    def test_product_bank_dedup_and_reporter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bank_path = Path(tmp) / "bank.json"
            added1, total1 = add_products_to_bank(
                bank_path,
                [
                    {
                        "name": "Kệ góc nhà tắm dán tường chịu lực",
                        "price_vnd": 35000,
                        "commission_rate": 0.12,
                        "shopee_affiliate_url": "https://s.shopee.vn/demo1",
                    },
                    {
                        "name": "Kệ góc nhà tắm dán tường chịu lực",
                        "price_vnd": 35000,
                        "commission_rate": 0.12,
                        "shopee_affiliate_url": "https://s.shopee.vn/demo1",
                    },
                ],
            )
            self.assertEqual((added1, total1), (1, 1))
            items = load_bank(bank_path)
            self.assertEqual(audit_post(items[0]["post"], "https://s.shopee.vn/demo1").verdict, "PASS")

        rep = build_report(period="3d", project_root=PROJECT_ROOT)
        self.assertTrue(Path(rep["report_path"]).exists())
        self.assertGreaterEqual(rep["total_bank"], 5)


if __name__ == "__main__":
    unittest.main()
