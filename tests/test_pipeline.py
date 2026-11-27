import tempfile
import unittest
from pathlib import Path

from src.compliance import validate_thread_bundle
from src.content_engine import generate_thread_bundle
from src.ctr_tracker import CTRTracker
from src.threads_client import ThreadsClient


class TestThreadsAffiliatePipeline(unittest.TestCase):
    def test_generate_and_validate_bundle(self):
        bundle = generate_thread_bundle()
        passed, errors = validate_thread_bundle(bundle)
        self.assertTrue(passed, f"Expected bundle to pass QA, got errors: {errors}")
        self.assertNotIn("http", bundle["main_post"].lower())
        self.assertIn("utm_source=threads", bundle["reply_link"])

    def test_compliance_rejects_url_in_main_post(self):
        bad_bundle = {
            "main_post": "Mua ngay tại https://shope.ee/test nhé",
            "reply_link": "https://shope.ee/test?utm_source=threads",
            "reply_engage": "Comment đi nào",
        }
        passed, errors = validate_thread_bundle(bad_bundle)
        self.assertFalse(passed)
        self.assertTrue(any("main_post contains a URL" in e for e in errors))

    def test_dry_run_publish_and_ctr_tracker(self):
        bundle = generate_thread_bundle()
        client = ThreadsClient(dry_run=True)
        res = client.publish_interactive_bundle(bundle)
        self.assertTrue(res["main_post_id"].startswith("dry_post_"))
        self.assertTrue(res["reply_link_id"].startswith("dry_reply_"))

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = CTRTracker(db_path=Path(tmpdir) / "test_ctr.db")
            row_id = tracker.log_post(bundle, res)
            self.assertGreater(row_id, 0)

            tracker.update_metrics(res["main_post_id"], impressions=1000, clicks=65, replies=18)
            leaderboard = tracker.get_hook_ctr_leaderboard()
            self.assertEqual(len(leaderboard), 1)
            self.assertEqual(leaderboard[0]["ctr_pct"], 6.5)


if __name__ == "__main__":
    unittest.main()
