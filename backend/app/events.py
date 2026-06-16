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
METRIC_TAG_PUBLISHED = "metric.tag.published"
METRIC_RUN_COMPLETED = "metric.run.completed"


def make_event_id(*parts: Any) -> str:
    raw = "|".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _post_event(url: str, secret: str, body: dict[str, Any], event_type: str, label: str) -> None:
    if not url:
        return
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-Hub-Secret"] = secret
    try:
        httpx.post(url, json=body, headers=headers, timeout=5.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s emit failed for %s: %s", label, event_type, exc)


def emit(event_type: str, payload: dict[str, Any], event_id: str | None = None) -> None:
    """Send an event to configured webhook targets. No-op when none configured."""
    body = {
        "source": "metricgraph",
        "event": event_type,
        "id": event_id or make_event_id(event_type, sorted(payload.items())),
        "ts": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    _post_event(
        settings.integration_webhook_url,
        settings.integration_webhook_secret,
        body,
        event_type,
        "Integration hub",
    )
    _post_event(
        settings.governance_webhook_url,
        settings.governance_webhook_secret,
        body,
        event_type,
        "Governance catalog",
    )
