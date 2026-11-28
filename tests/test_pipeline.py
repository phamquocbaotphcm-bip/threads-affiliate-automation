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
from src.growth_engine import run_growth_cycle
from src.scout_matcher import (
    has_buyer_intent,
    is_already_replied,
    load_scout_state,
    match_product_from_bank,
    record_scout_reply,
)
from src.watchdog import run_watchdog
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

        hashtag_post = dict(valid_post)
        hashtag_post["hashtags"] = "#tienich #phongtro #sinhvien"
        res_ht = audit_post(hashtag_post, "https://s.shopee.vn/test123")
        self.assertEqual(res_ht.verdict, "REJECT")
        self.assertLess(res_ht.naturalness_score, 85)

        caps_post = dict(valid_post)
        caps_post["body"] = "MUA NGAY HÔM NAY GIÁ SỐC cho phòng trọ sạch đẹp."
        res_caps = audit_post(caps_post, "https://s.shopee.vn/test123")
        self.assertEqual(res_caps.verdict, "REJECT")

        dup_res = audit_post(
            valid_post,
            "https://s.shopee.vn/test123",
            recent_texts=[
                "Đèn ngủ cảm biến giá rẻ cho phòng trọ.\n\nSạc USB dùng cả tháng, ánh sáng dịu không chói mắt.\n\nBạn thích đèn ánh sáng vàng hay trắng?\n\n#hoinghiendotienich"
            ],
        )
        self.assertEqual(dup_res.verdict, "REJECT")

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
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / "logs"
            midday = datetime(2026, 11, 27, 12, 30, tzinfo=timezone(timedelta(hours=7)))
            first = run_cycle(
                dry_run=True,
                simulate_self_heal=False,
                respect_schedule=True,
                now_local=midday,
                logs_dir=logs_dir,
            )
            self.assertEqual(first["total_posts"], 2)  # 08:30 & 12:30 only

            second = run_cycle(
                dry_run=True,
                simulate_self_heal=False,
                respect_schedule=True,
                now_local=midday,
                logs_dir=logs_dir,
            )
            self.assertEqual(second["total_posts"], 0)  # no duplicate publish

            full = run_cycle(dry_run=True, simulate_self_heal=True, logs_dir=logs_dir)
            self.assertEqual(full["total_posts"], 3)  # 3 posts/day cadence
            for item in full["results"]:
                self.assertEqual(item["verdict"], "PASS")
                self.assertTrue(item["ctr_above_target"])
            self.assertTrue((logs_dir / "learn.log").exists())
            self.assertTrue((logs_dir / "insights_report.json").exists())

    def test_product_bank_dedup_and_reporter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            bank_path = tmp_root / "data" / "product_bank_90d.json"
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

            rep = build_report(period="3d", project_root=tmp_root)
            self.assertTrue(Path(rep["report_path"]).exists())
            self.assertEqual(rep["total_bank"], 1)

    def test_watchdog_healthy_recovery_and_low_bank_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            logs_dir = tmp_root / "logs"
            bank_path = tmp_root / "data" / "product_bank_90d.json"
            items = [
                {
                    "name": f"Sản phẩm tiện ích {i}",
                    "price_vnd": 35000,
                    "commission_rate": 0.12,
                    "shopee_affiliate_url": f"https://s.shopee.vn/wd{i}",
                }
                for i in range(16)
            ]
            add_products_to_bank(bank_path, items)

            # 08:30 missed at 09:30 -> Watchdog recovers it
            morning = datetime(2026, 11, 28, 9, 30, tzinfo=timezone(timedelta(hours=7)))
            res_recover = run_watchdog(
                dry_run=True,
                auto_recover=True,
                now_local=morning,
                logs_dir=logs_dir,
                bank_path=bank_path,
            )
            self.assertEqual(res_recover["status"], "RECOVERED")
            self.assertEqual(res_recover["recovered_posts"], 1)

            # Second check at 09:45 -> already published, stays HEALTHY
            res_ok = run_watchdog(
                dry_run=True,
                auto_recover=True,
                now_local=datetime(2026, 11, 28, 9, 45, tzinfo=timezone(timedelta(hours=7))),
                logs_dir=logs_dir,
                bank_path=bank_path,
            )
            self.assertEqual(res_ok["status"], "HEALTHY")

            # Now remaining links = 15 -> if 1 more is marked published -> 14 < 15 -> ALERT
            state_file = logs_dir / "published_state.json"
            state = json.loads(state_file.read_text(encoding="utf-8"))
            state["published_urls"].append("https://s.shopee.vn/wd99_extra")
            # Actually reduce bank to 10 items to trigger LOW_BANK
            add_products_to_bank(tmp_root / "data" / "small_bank.json", items[:5])
            res_alert = run_watchdog(
                dry_run=True,
                auto_recover=False,
                now_local=morning,
                logs_dir=logs_dir,
                bank_path=tmp_root / "data" / "small_bank.json",
            )
            self.assertEqual(res_alert["status"], "ALERT")
            self.assertTrue(any("LOW_BANK" in a for a in res_alert["alerts"]))

    def test_growth_engine_and_viral_bank_qa(self) -> None:
        viral_bank = json.loads(
            (PROJECT_ROOT / "data" / "viral_organic_bank.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(viral_bank), 30)
        for post in viral_bank:
            probe = dict(post)
            probe["affiliate_comment_cta"] = "organic {affiliate_url}"
            res = audit_post(probe, "https://s.shopee.vn/organic")
            self.assertEqual(res.verdict, "PASS", msg=f"{post['id']} failed: {res.defects}")

        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / "logs"
            evening = datetime(2026, 11, 28, 17, 35, tzinfo=timezone(timedelta(hours=7)))
            first = run_growth_cycle(
                dry_run=True,
                publish_viral=True,
                now_local=evening,
                logs_dir=logs_dir,
            )
            self.assertTrue(first["viral_post"]["published"])
            self.assertTrue((logs_dir / "growth_metrics.json").exists())

            second = run_growth_cycle(
                dry_run=True,
                publish_viral=True,
                now_local=evening,
                logs_dir=logs_dir,
            )
            self.assertFalse(second["viral_post"]["published"])
            self.assertEqual(second["viral_post"]["reason"], "already_published_today")

    def test_auto_rewrite_and_skip_rejected_sku(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            logs_dir = tmp_root / "logs"
            bank_path = tmp_root / "data" / "product_bank_90d.json"
            bank_path.parent.mkdir(parents=True, exist_ok=True)
            bank_path.write_text(
                json.dumps(
                    [
                        {
                            "sku": "BAD-01",
                            "name": "Sản phẩm lỗi",
                            "price_vnd": 50000,
                            "commission_rate": 0.1,
                            "shopee_affiliate_url": "https://s.shopee.vn/bad1",
                            "post": {
                                "id": "BAD-01",
                                "hook": "Không thể phủ nhận món này quá đỉnh",
                                "body": "Cam kết 100% sự lựa chọn hoàn hảo cho bạn.",
                                "engagement_question": "Thích không?",
                                "affiliate_comment_cta": "Link: {affiliate_url}",
                                "hashtags": "#a #b #c",
                            },
                        },
                        {
                            "sku": "GOOD-02",
                            "name": "Kệ để bàn gấp gọn",
                            "price_vnd": 65000,
                            "commission_rate": 0.12,
                            "shopee_affiliate_url": "https://s.shopee.vn/good2",
                            "image_url": "https://example.com/ke.jpg",
                            "post": {
                                "id": "GOOD-02",
                                "hook": "Bàn học nhỏ xíu mà để sách vở hay bị chật.",
                                "body": "Thêm cái kệ nhỏ 65k xếp chồng lên nhìn góc bàn thoáng hẳn luôn.",
                                "engagement_question": "Góc bàn của bạn đang để mấy món đồ?",
                                "affiliate_comment_cta": "Link kệ mình để đây nha: {affiliate_url}",
                                "hashtags": "",
                                "topic_tag": "Đồ tiện ích",
                            },
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            # Run at 20:30 when 08:30, 12:30, 20:30 are all due, BAD-01 gets auto-rewritten & passes!
            res = run_cycle(
                dry_run=True,
                simulate_self_heal=False,
                respect_schedule=True,
                now_local=datetime(2026, 11, 28, 20, 35, tzinfo=timezone(timedelta(hours=7))),
                logs_dir=logs_dir,
                bank_path=bank_path,
            )
            passed = [r for r in res["results"] if r["verdict"] == "PASS"]
            self.assertEqual(len(passed), 2)
            self.assertEqual(passed[1]["publish"]["media_type"], "TEXT")  # 12:30 -> TEXT-only

    def test_scout_matcher_intent_dedup_and_match(self) -> None:
        self.assertTrue(has_buyer_intent("Mình xin link bình giữ nhiệt gọn nhẹ nha"))
        self.assertFalse(has_buyer_intent("Hôm nay trời đẹp quá mọi người ơi"))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            bank_path = tmp_root / "data" / "product_bank_90d.json"
            state_path = tmp_root / "logs" / "scout_replies_state.json"
            add_products_to_bank(
                bank_path,
                [
                    {
                        "sku": "MATCH-01",
                        "name": "Bình giữ nhiệt inox 304 LocknLock 500ml",
                        "price_vnd": 199000,
                        "commission_rate": 0.10,
                        "shopee_affiliate_url": "https://s.shopee.vn/match01",
                    },
                    {
                        "sku": "MATCH-02",
                        "name": "Đèn bàn học chống cận LED cảm ứng",
                        "price_vnd": 149000,
                        "commission_rate": 0.12,
                        "shopee_affiliate_url": "https://s.shopee.vn/match02",
                    },
                ],
            )
            matched = match_product_from_bank(
                "Xin link bình giữ nhiệt inox giữ nóng tốt với ạ",
                bank_path=bank_path,
            )
            self.assertIsNotNone(matched)
            self.assertEqual(matched["shopee_affiliate_url"], "https://s.shopee.vn/match01")

            now = datetime(2026, 11, 28, 21, 15, tzinfo=timezone.utc)
            state_before = load_scout_state(state_path)
            self.assertFalse(is_already_replied(state_before, "https://www.threads.com/@u1/post/1", "u1", "2026-11-28"))

            record_scout_reply(
                state_path,
                "https://www.threads.com/@u1/post/1",
                "@u1",
                "MATCH-01",
                "https://s.shopee.vn/match01",
                now_utc=now,
            )
            state_after = load_scout_state(state_path)
            self.assertTrue(is_already_replied(state_after, "https://www.threads.com/@u1/post/1?x=1", "u1", "2026-11-28"))
            self.assertTrue(is_already_replied(state_after, "https://www.threads.com/@u1/post/2", "u1", "2026-11-28"))


if __name__ == "__main__":
    unittest.main()
