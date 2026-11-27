"""
Content Engine (Core_MKT)
Generates high-CTR interactive Threads posts + auto-reply affiliate chains.
Uses a zero-cost local template engine by default, with UTM tracking for CTR attribution.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl


BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTS_PATH = BASE_DIR / "config" / "products.json"
HOOKS_PATH = BASE_DIR / "config" / "hooks.json"


def load_products(path: Path = PRODUCTS_PATH) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        products = json.load(f)
    return [p for p in products if p.get("status") == "active"]


def load_hooks(path: Path = HOOKS_PATH) -> List[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("hooks", [])


def build_tracked_url(base_url: str, product_id: str, hook_id: str) -> str:
    """Append UTM parameters for exact CTR attribution by product and hook variant."""
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query))
    query.update(
        {
            "utm_source": "threads",
            "utm_medium": "auto_reply",
            "utm_campaign": f"{product_id}_{hook_id}",
        }
    )
    new_query = urlencode(query)
    return urlunparse(parsed._replace(query=new_query))


from src.link_scraper import load_products_from_links_file


def generate_thread_bundle(
    product: Optional[Dict] = None,
    hook: Optional[Dict] = None,
    links_file: Optional[Path] = None,
    fetch_remote: bool = True,
) -> Dict:
    """
    Generate a 3-part interactive Threads bundle:
      1. main_post: Hook + curiosity/debate question (NO link -> max organic reach)
      2. reply_link: Soft CTA + UTM-tracked affiliate link (drives CTR)
      3. reply_engage: Follow-up engagement prompt (boosts thread velocity)
    """
    products = load_products_from_links_file(
        file_path=links_file, fetch_remote=fetch_remote
    )
    if not products:
        products = load_products()
    hooks = load_hooks()

    if not products:
        raise ValueError("No active products found in product_links.txt or products.json")
    if not hooks:
        raise ValueError("No hook templates found in config/hooks.json")

    selected_product = product or random.choice(products)
    selected_hook = hook or random.choice(hooks)

    price_k = round(selected_product["price_vnd"] / 1000)
    tracked_url = build_tracked_url(
        selected_product["affiliate_url"],
        selected_product["id"],
        selected_hook["id"],
    )

    context = {
        "name": selected_product["name"],
        "pain_point": selected_product["pain_point"],
        "benefit": selected_product["benefit"],
        "price_k": price_k,
        "tracked_url": tracked_url,
    }

    return {
        "product_id": selected_product["id"],
        "product_name": selected_product["name"],
        "platform": selected_product["platform"],
        "hook_id": selected_hook["id"],
        "hook_angle": selected_hook["angle"],
        "tracked_url": tracked_url,
        "main_post": selected_hook["main_template"].format(**context),
        "reply_link": selected_hook["reply_link_template"].format(**context),
        "reply_engage": selected_hook["reply_engage_template"].format(**context),
    }
