"""Shopee Affiliate product catalog & link validation/signing (Core_ECOM)."""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

SHOPEE_GRAPHQL_URL = "https://open-api.affiliate.shopee.vn/graphql"
VALID_AFFILIATE_HOSTS = ("s.shopee.vn", "shope.ee", "shopee.vn")


def load_products(products_path: Path) -> Dict[str, Dict[str, Any]]:
    """Load product catalog keyed by SKU."""
    items: List[Dict[str, Any]] = json.loads(
        Path(products_path).read_text(encoding="utf-8")
    )
    return {item["sku"]: item for item in items}


def is_valid_affiliate_url(url: str) -> bool:
    """Validate that url is HTTPS and points to an allowed Shopee domain."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https":
        return False
    host = parsed.netloc.lower()
    return any(host == d or host.endswith(f".{d}") for d in VALID_AFFILIATE_HOSTS)


def is_placeholder_url(url: str) -> bool:
    """Return True if the affiliate link still uses the template placeholder."""
    return "REPLACE_WITH_YOUR_LINK" in url


def build_shopee_auth_header(
    app_id: str,
    app_secret: str,
    payload_str: str,
    timestamp: Optional[int] = None,
) -> str:
    """Build SHA256 Authorization header required by Shopee Affiliate Open API."""
    ts = timestamp if timestamp is not None else int(time.time())
    factor = f"{app_id}{ts}{payload_str}{app_secret}"
    signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()
    return f"SHA256 Credential={app_id}, Timestamp={ts}, Signature={signature}"


def generate_short_link(
    origin_url: str,
    sub_ids: Optional[List[str]] = None,
    dry_run: bool = True,
) -> str:
    """Generate a Shopee Affiliate short link via GraphQL API or dry-run stub."""
    if dry_run:
        digest = hashlib.sha256(origin_url.encode("utf-8")).hexdigest()[:8]
        return f"https://s.shopee.vn/dryrun_{digest}"

    app_id = os.getenv("SHOPEE_APP_ID", "").strip()
    app_secret = os.getenv("SHOPEE_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise ValueError("Missing SHOPEE_APP_ID or SHOPEE_APP_SECRET in environment")

    query = (
        'mutation { generateShortLink(input: { originUrl: "%s", subIds: %s }) '
        "{ shortLink } }"
    ) % (origin_url, json.dumps(sub_ids or ["hoinghiendotienich"]))
    payload_str = json.dumps({"query": query}, separators=(",", ":"))
    auth_header = build_shopee_auth_header(app_id, app_secret, payload_str)

    req = urllib.request.Request(
        SHOPEE_GRAPHQL_URL,
        data=payload_str.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": auth_header,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        body = json.loads(resp.read().decode("utf-8"))
    return body["data"]["generateShortLink"]["shortLink"]
