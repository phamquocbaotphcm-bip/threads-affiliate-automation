"""Self-healing execution, Circuit Breaker (max 3 retries), and Learn Logger."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a task fails consecutively beyond max_retries."""


class RecoverableTaskError(RuntimeError):
    """Raised for known recoverable errors that trigger auto-fix and retry."""

    def __init__(self, error_type: str, message: str, root_cause: str = "") -> None:
        super().__init__(message)
        self.error_type = error_type
        self.root_cause = root_cause or message


@dataclass
class LearnEntry:
    """Structured lesson learned record for logs/learn.log and learn_kb.json."""

    timestamp: str
    error_type: str
    context: str
    root_cause: str
    auto_fix: str
    prevention_rule: str
    resolved: bool


class LearnLogger:
    """Persists self-healing events to human-readable learn.log and JSON KB."""

    def __init__(self, logs_dir: Path) -> None:
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.logs_dir / "learn.log"
        self.kb_path = self.logs_dir / "learn_kb.json"

    def record(
        self,
        error_type: str,
        context: str,
        root_cause: str,
        auto_fix: str,
        prevention_rule: str,
        resolved: bool,
    ) -> LearnEntry:
        """Append a structured lesson entry to both learn.log and learn_kb.json."""
        entry = LearnEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            error_type=error_type,
            context=context,
            root_cause=root_cause,
            auto_fix=auto_fix,
            prevention_rule=prevention_rule,
            resolved=resolved,
        )
        line = (
            f"[{entry.timestamp}] [{entry.error_type}] resolved={entry.resolved} | "
            f"context={entry.context} | root_cause={entry.root_cause} | "
            f"auto_fix={entry.auto_fix} | prevention={entry.prevention_rule}\n"
        )
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line)

        kb: List[Dict[str, Any]] = []
        if self.kb_path.exists():
            try:
                kb = json.loads(self.kb_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                kb = []
        kb.append(asdict(entry))
        self.kb_path.write_text(
            json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return entry


DEFAULT_FIX_STRATEGIES: Dict[str, Dict[str, str]] = {
    "TOKEN_EXPIRED": {
        "auto_fix": "Refresh long-lived Threads OAuth token and retry request",
        "prevention_rule": "Proactively refresh token when remaining TTL < 7 days",
    },
    "RATE_LIMIT": {
        "auto_fix": "Apply exponential backoff before next API call",
        "prevention_rule": "Enforce minimum spacing between scheduled Threads posts",
    },
    "INVALID_AFFILIATE_LINK": {
        "auto_fix": "Fallback to verified Shopee short-link or pause SKU until updated",
        "prevention_rule": "Validate s.shopee.vn/shope.ee domain in Core_ECOM pre-check",
    },
    "COMPLIANCE_VIOLATION": {
        "auto_fix": "Strip banned keywords/inline links and re-run Core_QA_Audit",
        "prevention_rule": "Keep affiliate links strictly in affiliate_comment_cta",
    },
    "NETWORK_ERROR": {
        "auto_fix": "Retry with bounded backoff",
        "prevention_rule": "Use request timeout and transient retry guard",
    },
}


class SelfHealingExecutor:
    """Executes tasks with automatic recovery and a 3-attempt Circuit Breaker."""

    def __init__(
        self,
        learn_logger: LearnLogger,
        max_retries: int = 3,
        backoff_seconds: float = 0.05,
        fix_handlers: Optional[Dict[str, Callable[[RecoverableTaskError], None]]] = None,
    ) -> None:
        self.learn_logger = learn_logger
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.fix_handlers = fix_handlers or {}

    def run(
        self,
        context: str,
        fn: Callable[[], Any],
    ) -> Any:
        """Run fn with up to max_retries attempts; escalate if all fail."""
        last_exc: Optional[Exception] = None
        last_error_type: Optional[str] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = fn()
                if attempt > 1 and last_error_type is not None:
                    strategy = DEFAULT_FIX_STRATEGIES.get(
                        last_error_type,
                        {
                            "auto_fix": "Retry succeeded",
                            "prevention_rule": "Keep transient retry guard",
                        },
                    )
                    self.learn_logger.record(
                        error_type=last_error_type,
                        context=f"{context} (recovered on attempt {attempt}/{self.max_retries})",
                        root_cause="Resolved after auto-fix and retry",
                        auto_fix=strategy["auto_fix"],
                        prevention_rule=strategy["prevention_rule"],
                        resolved=True,
                    )
                return result
            except RecoverableTaskError as exc:
                last_exc = exc
                last_error_type = exc.error_type
                strategy = DEFAULT_FIX_STRATEGIES.get(
                    exc.error_type,
                    {
                        "auto_fix": "Log error and retry operation",
                        "prevention_rule": "Inspect root cause before re-enabling",
                    },
                )
                handler = self.fix_handlers.get(exc.error_type)
                if handler is not None:
                    handler(exc)

                self.learn_logger.record(
                    error_type=exc.error_type,
                    context=f"{context} (attempt {attempt}/{self.max_retries})",
                    root_cause=exc.root_cause,
                    auto_fix=strategy["auto_fix"],
                    prevention_rule=strategy["prevention_rule"],
                    resolved=False,
                )
                if attempt < self.max_retries and self.backoff_seconds > 0:
                    time.sleep(self.backoff_seconds * attempt)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                last_error_type = type(exc).__name__
                self.learn_logger.record(
                    error_type=last_error_type,
                    context=f"{context} (attempt {attempt}/{self.max_retries})",
                    root_cause=str(exc),
                    auto_fix="Unhandled exception logged for Core_IT inspection",
                    prevention_rule="Add explicit validation guard for this failure mode",
                    resolved=False,
                )
                if attempt < self.max_retries and self.backoff_seconds > 0:
                    time.sleep(self.backoff_seconds * attempt)

        raise CircuitBreakerOpenError(
            f"Circuit breaker tripped for '{context}' after {self.max_retries} "
            f"consecutive failures: {last_exc}"
        )
