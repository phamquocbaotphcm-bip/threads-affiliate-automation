"""Threads Graph API OAuth 2.0 & Token Auto-Refresh (Core_IT)."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Optional

THREADS_AUTH_URL = "https://threads.net/oauth/authorize"
THREADS_TOKEN_URL = "https://graph.threads.net/oauth/access_token"
THREADS_LONG_LIVED_URL = "https://graph.threads.net/access_token"
THREADS_REFRESH_URL = "https://graph.threads.net/refresh_access_token"
DEFAULT_SCOPES = (
    "threads_basic,threads_content_publish,"
    "threads_manage_replies,threads_manage_insights"
)


@dataclass
class ThreadsAuthConfig:
    """OAuth configuration loaded from environment variables."""

    app_id: str
    app_secret: str
    redirect_uri: str
    user_id: str
    access_token: str

    @classmethod
    def from_env(cls) -> "ThreadsAuthConfig":
        return cls(
            app_id=os.getenv("THREADS_APP_ID", "").strip(),
            app_secret=os.getenv("THREADS_APP_SECRET", "").strip(),
            redirect_uri=os.getenv(
                "THREADS_REDIRECT_URI", "https://localhost/callback"
            ).strip(),
            user_id=os.getenv("THREADS_USER_ID", "").strip(),
            access_token=os.getenv("THREADS_ACCESS_TOKEN", "").strip(),
        )


def build_authorization_url(
    config: ThreadsAuthConfig,
    scopes: str = DEFAULT_SCOPES,
    state: str = "hoinghiendotienich",
) -> str:
    """Build Meta Threads OAuth 2.0 authorization URL for Admin consent."""
    params = urllib.parse.urlencode(
        {
            "client_id": config.app_id,
            "redirect_uri": config.redirect_uri,
            "scope": scopes,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{THREADS_AUTH_URL}?{params}"


def _http_json(url: str, data: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=encoded, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def exchange_code_for_long_lived_token(
    config: ThreadsAuthConfig,
    code: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Exchange OAuth authorization code for short-lived then 60-day token."""
    if dry_run:
        return {
            "access_token": "DRY_RUN_LONG_LIVED_TOKEN",
            "token_type": "bearer",
            "expires_in": 5184000,
        }

    short_resp = _http_json(
        THREADS_TOKEN_URL,
        data={
            "client_id": config.app_id,
            "client_secret": config.app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": config.redirect_uri,
            "code": code,
        },
    )
    short_token = short_resp["access_token"]
    query = urllib.parse.urlencode(
        {
            "grant_type": "th_exchange_token",
            "client_secret": config.app_secret,
            "access_token": short_token,
        }
    )
    return _http_json(f"{THREADS_LONG_LIVED_URL}?{query}")


def refresh_long_lived_token(
    access_token: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """Refresh an existing long-lived Threads token before expiration."""
    if dry_run:
        return {
            "access_token": "DRY_RUN_REFRESHED_TOKEN",
            "token_type": "bearer",
            "expires_in": 5184000,
        }

    query = urllib.parse.urlencode(
        {
            "grant_type": "th_refresh_token",
            "access_token": access_token,
        }
    )
    return _http_json(f"{THREADS_REFRESH_URL}?{query}")
