"""
Zero-Dependency MCP Server (Model Context Protocol over stdio / JSON-RPC 2.0)
Exposes the Threads Affiliate Automation pipeline as MCP tools for local AI clients
(Antigravity Desktop, Cursor, Claude Desktop, etc.) for @hoinghiendotienich.
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

from src.compliance import validate_thread_bundle
from src.content_engine import generate_thread_bundle
from src.ctr_tracker import CTRTracker
from src.link_scraper import DEFAULT_LINKS_FILE, inspect_product_link
from src.threads_client import ThreadsClient


SERVER_INFO = {
    "name": "threads-affiliate-mcp",
    "version": "1.0.0",
}

TOOLS = [
    {
        "name": "generate_threads_post",
        "description": "Generate a high-CTR 3-step interactive Threads bundle (Main Post without link + Reply 1 affiliate link + Reply 2 engagement) for @hoinghiendotienich.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_url": {
                    "type": "string",
                    "description": "Optional specific affiliate URL. If omitted, picks from config/product_links.txt.",
                },
                "product_name": {
                    "type": "string",
                    "description": "Optional product name hint.",
                },
                "price_hint": {
                    "type": "string",
                    "description": "Optional price hint, e.g. '149k'.",
                },
            },
        },
    },
    {
        "name": "publish_threads_post",
        "description": "Validate and publish a 3-step interactive Threads post (dry_run=true by default; set live=true to publish to Threads API).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "live": {
                    "type": "boolean",
                    "description": "Set true to publish live using THREADS_USER_ID and THREADS_ACCESS_TOKEN env vars.",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "add_product_link",
        "description": "Append a new affiliate product link to config/product_links.txt.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Affiliate URL (e.g. https://shope.ee/...)"},
                "name": {"type": "string", "description": "Short product name"},
                "price": {"type": "string", "description": "Price string, e.g. '149k'"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_ctr_leaderboard",
        "description": "Get CTR performance leaderboard ranked by Hook variant from SQLite tracker.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _handle_tool_call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if name == "generate_threads_post":
        product = None
        if args.get("product_url"):
            product = inspect_product_link(
                url=args["product_url"],
                hint_name=args.get("product_name", ""),
                hint_price=args.get("price_hint", ""),
                fetch_remote=True,
            )
        bundle = generate_thread_bundle(product=product)
        passed, errors = validate_thread_bundle(bundle)
        return {"qa_passed": passed, "qa_errors": errors, "bundle": bundle}

    if name == "publish_threads_post":
        live = bool(args.get("live", False))
        bundle = generate_thread_bundle()
        passed, errors = validate_thread_bundle(bundle)
        if not passed:
            return {"status": "REJECTED", "errors": errors}
        client = ThreadsClient(dry_run=not live)
        res = client.publish_interactive_bundle(bundle)
        tracker = CTRTracker()
        row_id = tracker.log_post(bundle, res)
        return {"status": "DONE", "live": live, "db_row_id": row_id, "result": res, "bundle": bundle}

    if name == "add_product_link":
        url = args["url"].strip()
        parts = [url]
        if args.get("name"):
            parts.append(args["name"].strip())
        if args.get("price"):
            parts.append(args["price"].strip())
        line = " | ".join(parts)
        Path(DEFAULT_LINKS_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(DEFAULT_LINKS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{line}\n")
        return {"status": "ADDED", "file": str(DEFAULT_LINKS_FILE), "entry": line}

    if name == "get_ctr_leaderboard":
        tracker = CTRTracker()
        return {"leaderboard": tracker.get_hook_ctr_leaderboard()}

    raise ValueError(f"Unknown tool: {name}")


def handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params") or {}

    try:
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments") or {}
            payload = _handle_tool_call(tool_name, tool_args)
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}
                ]
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        if "id" not in req:
            continue  # JSON-RPC notification
        resp = handle_request(req)
        sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
