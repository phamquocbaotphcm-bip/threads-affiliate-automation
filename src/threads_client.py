"""
Threads Graph API Client (Core_IT)
Publishes interactive Threads posts + auto-reply affiliate chains using Meta's official Threads API.
Zero external dependencies (uses Python stdlib urllib). Defaults to DRY_RUN=True for safety.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional


THREADS_API_BASE = "https://graph.threads.net/v1.0"


class ThreadsAPIError(Exception):
    """Raised when Threads Graph API returns an error."""


class ThreadsClient:
    def __init__(
        self,
        user_id: Optional[str] = None,
        access_token: Optional[str] = None,
        dry_run: bool = True,
    ):
        self.user_id = user_id or os.getenv("THREADS_USER_ID", "")
        self.access_token = access_token or os.getenv("THREADS_ACCESS_TOKEN", "")
        self.dry_run = dry_run

        if not self.dry_run and (not self.user_id or not self.access_token):
            raise ValueError(
                "THREADS_USER_ID and THREADS_ACCESS_TOKEN must be set when dry_run=False"
            )

    def _post(self, endpoint: str, params: Dict[str, str]) -> Dict:
        url = f"{THREADS_API_BASE}/{endpoint.lstrip('/')}"
        payload = dict(params)
        payload["access_token"] = self.access_token
        encoded = urllib.parse.urlencode(payload).encode("utf-8")

        req = urllib.request.Request(url, data=encoded, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise ThreadsAPIError(f"HTTP {e.code} on {endpoint}: {body}") from e
        except urllib.error.URLError as e:
            raise ThreadsAPIError(f"Network error on {endpoint}: {e.reason}") from e

    def create_text_post(self, text: str, reply_to_id: Optional[str] = None) -> str:
        """Create and publish a single Threads text post (or reply). Returns published post ID."""
        if self.dry_run:
            prefix = "dry_reply" if reply_to_id else "dry_post"
            return f"{prefix}_{int(time.time() * 1000)}"

        container_params = {
            "media_type": "TEXT",
            "text": text,
        }
        if reply_to_id:
            container_params["reply_to_id"] = reply_to_id

        container = self._post(f"{self.user_id}/threads", container_params)
        creation_id = container.get("id")
        if not creation_id:
            raise ThreadsAPIError(f"Missing creation_id in response: {container}")

        # Brief wait recommended by Meta Threads API before publishing container
        time.sleep(2)
        published = self._post(
            f"{self.user_id}/threads_publish",
            {"creation_id": creation_id},
        )
        post_id = published.get("id")
        if not post_id:
            raise ThreadsAPIError(f"Missing published post id in response: {published}")
        return post_id

    def publish_interactive_bundle(self, bundle: Dict) -> Dict[str, str]:
        """
        Publish the full 3-step high-CTR interactive thread:
          1. Main Hook Post (no link)
          2. Reply 1: Affiliate Link + Soft CTA
          3. Reply 2: Engagement Trigger
        """
        main_id = self.create_text_post(bundle["main_post"])
        reply_link_id = self.create_text_post(bundle["reply_link"], reply_to_id=main_id)

        reply_engage_id = ""
        if bundle.get("reply_engage"):
            reply_engage_id = self.create_text_post(
                bundle["reply_engage"], reply_to_id=main_id
            )

        return {
            "main_post_id": main_id,
            "reply_link_id": reply_link_id,
            "reply_engage_id": reply_engage_id,
            "dry_run": str(self.dry_run),
        }
