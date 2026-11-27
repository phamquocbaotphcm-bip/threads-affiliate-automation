"""
CTR & Engagement Tracker (Core_MKT + Core_IT)
Lightweight SQLite database to log published threads, track impressions/clicks/CTR,
and rank the best-performing Hook x Product combinations.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "ctr_metrics.db"


class CTRTracker:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    published_at TEXT NOT NULL,
                    main_post_id TEXT NOT NULL,
                    product_id TEXT NOT NULL,
                    product_name TEXT NOT NULL,
                    hook_id TEXT NOT NULL,
                    tracked_url TEXT NOT NULL,
                    dry_run INTEGER NOT NULL DEFAULT 1,
                    impressions INTEGER NOT NULL DEFAULT 0,
                    clicks INTEGER NOT NULL DEFAULT 0,
                    replies INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def log_post(self, bundle: Dict, publish_result: Dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO posts (
                    published_at, main_post_id, product_id, product_name,
                    hook_id, tracked_url, dry_run
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    publish_result["main_post_id"],
                    bundle["product_id"],
                    bundle["product_name"],
                    bundle["hook_id"],
                    bundle["tracked_url"],
                    1 if str(publish_result.get("dry_run", "True")).lower() == "true" else 0,
                ),
            )
            return int(cur.lastrowid)

    def update_metrics(
        self, main_post_id: str, impressions: int, clicks: int, replies: int = 0
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE posts
                SET impressions = ?, clicks = ?, replies = ?
                WHERE main_post_id = ?
                """,
                (impressions, clicks, replies, main_post_id),
            )

    def get_hook_ctr_leaderboard(self) -> List[Dict]:
        """Return hooks ranked by CTR (%) to automatically optimize future posts."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    hook_id,
                    COUNT(*) AS total_posts,
                    SUM(impressions) AS total_impressions,
                    SUM(clicks) AS total_clicks,
                    CASE
                        WHEN SUM(impressions) > 0
                        THEN ROUND(CAST(SUM(clicks) AS REAL) * 100.0 / SUM(impressions), 2)
                        ELSE 0.0
                    END AS ctr_pct
                FROM posts
                GROUP BY hook_id
                ORDER BY ctr_pct DESC, total_clicks DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]
