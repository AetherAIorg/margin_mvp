"""Best-effort outbound event emitter to the integration hub.

Posts normalized events to the configured integration hub so they can be
fanned out to Slack/Teams/Linear. Emission is fire-and-forget: any failure is
swallowed and logged so it can never break the parse pipeline or API requests.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Event type constants (mirrored in integration_hub/app/events.py).
ISSUE_DETECTED = "issue.detected"
PARSE_FAILED = "parse.failed"
METRIC_CANDIDATE_DISCOVERED = "metric.candidate.discovered"
METRIC_APPROVED = "metric.approved"
METRIC_RUN_COMPLETED = "metric.run.completed"


def make_event_id(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def emit(event_type: str, payload: dict[str, Any], event_id: str | None = None) -> None:
    """Send an event to the integration hub. No-op when not configured."""
    url = settings.integration_webhook_url
    if not url:
        return
    body = {
        "source": "metricgraph",
        "event": event_type,
        "id": event_id or make_event_id(event_type, sorted(payload.items())),
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    headers = {"Content-Type": "application/json"}
    if settings.integration_webhook_secret:
        headers["X-Hub-Secret"] = settings.integration_webhook_secret
    try:
        httpx.post(url, json=body, headers=headers, timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Integration hub emit failed for %s: %s", event_type, exc)
