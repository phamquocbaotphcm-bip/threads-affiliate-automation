"""
Link Scraper & Product Extractor (Satellite Agent / Sub_Researcher)
Reads affiliate product links from a designated file (default: config/product_links.txt),
fetches page metadata (title, og:title, og:description) with graceful fallback to URL slug
or inline notes when e-commerce sites block bots.
"""

import hashlib
import html
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LINKS_FILE = BASE_DIR / "config" / "product_links.txt"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "shopee" in host or "shope.ee" in host:
        return "Shopee"
    if "tiktok" in host:
        return "TikTokShop"
    if "lazada" in host or "laz.co" in host:
        return "Lazada"
    if "tiki" in host:
        return "Tiki"
    return "Affiliate"


def parse_price_vnd(text: str) -> int:
    """Extract approximate price in VND from text like '189k' or '245.000đ'."""
    m_k = re.search(r"(\d{2,4})\s*k\b", text, re.IGNORECASE)
    if m_k:
        return int(m_k.group(1)) * 1000
    m_vnd = re.search(r"(\d{1,3}(?:[.,]\d{3})+)", text)
    if m_vnd:
        digits = re.sub(r"[.,]", "", m_vnd.group(1))
        return int(digits)
    return 199000


def parse_links_file(file_path: Optional[Path] = None) -> List[Dict[str, str]]:
    """
    Parse product links file. Each non-comment line supports:
      URL
      URL | Product Name
      URL | Product Name | Price (e.g. 189k)
    """
    env_path = os.getenv("PRODUCT_LINKS_FILE")
    path = Path(file_path) if file_path else (BASE_DIR / env_path if env_path else DEFAULT_LINKS_FILE)
    if not path.exists():
        return []

    entries: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            url = parts[0]
            if not url.startswith(("http://", "https://")):
                continue
            entries.append(
                {
                    "url": url,
                    "hint_name": parts[1] if len(parts) > 1 else "",
                    "hint_price": parts[2] if len(parts) > 2 else "",
                }
            )
    return entries


def _extract_meta(page_html: str) -> Dict[str, str]:
    og_title = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        page_html,
        re.IGNORECASE,
    )
    og_desc = re.search(
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        page_html,
        re.IGNORECASE,
    )
    title_tag = re.search(r"<title[^>]*>(.*?)</title>", page_html, re.IGNORECASE | re.DOTALL)

    title = ""
    if og_title:
        title = html.unescape(og_title.group(1)).strip()
    elif title_tag:
        title = html.unescape(re.sub(r"\s+", " ", title_tag.group(1))).strip()

    desc = html.unescape(og_desc.group(1)).strip() if og_desc else ""
    return {"title": title, "description": desc}


def _name_from_url_slug(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "Sản phẩm hot trend đang giảm giá"
    slug = path.split("/")[-1]
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\b(example|i\.\d+\.\d+)\b", "", slug, flags=re.IGNORECASE).strip()
    return slug.capitalize() if slug else "Sản phẩm tiện ích đang hot"


def inspect_product_link(
    url: str,
    hint_name: str = "",
    hint_price: str = "",
    fetch_remote: bool = True,
    timeout: int = 3,
) -> Dict:
    """
    Inspect an affiliate link and return a normalized product dictionary
    ready for content_engine.py.
    """
    fetched_title = ""
    fetched_desc = ""
    final_url = url

    if fetch_remote:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" in content_type.lower():
                    raw_html = resp.read(150_000).decode("utf-8", errors="ignore")
                    meta = _extract_meta(raw_html)
                    fetched_title = meta["title"]
                    fetched_desc = meta["description"]
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            # Graceful fallback when e-commerce sites block automated requests
            pass

    name = hint_name or fetched_title or _name_from_url_slug(final_url)
    price_vnd = parse_price_vnd(f"{hint_price} {fetched_title} {fetched_desc}")
    platform = detect_platform(final_url)
    short_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:6]

    pain_point = (
        f"tốn thời gian tìm một mẫu {name.lower()} vừa bền vừa đúng giá"
        if not fetched_desc
        else f"khó chọn được sản phẩm ưng ý cho nhu cầu hằng ngày"
    )
    benefit = (
        fetched_desc[:120].strip()
        if fetched_desc
        else f"thiết kế gọn nhẹ, giải quyết đúng nhu cầu thực tế và đang có deal tốt trên {platform}"
    )

    return {
        "id": f"link_{short_hash}",
        "name": name,
        "category": "auto_link",
        "platform": platform,
        "price_vnd": price_vnd,
        "commission_pct": 10.0,
        "pain_point": pain_point,
        "benefit": benefit,
        "affiliate_url": url,
        "status": "active",
    }


def load_products_from_links_file(
    file_path: Optional[Path] = None, fetch_remote: bool = True
) -> List[Dict]:
    entries = parse_links_file(file_path)
    return [
        inspect_product_link(
            url=e["url"],
            hint_name=e["hint_name"],
            hint_price=e["hint_price"],
            fetch_remote=fetch_remote,
        )
        for e in entries
    ]
