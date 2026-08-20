from __future__ import annotations

import logging

from theorycraft.graph.state import NotificationResult, TheoryCraftState
from theorycraft.telemetry.langfuse import node_trace

logger = logging.getLogger(__name__)


def _build_payload(state: TheoryCraftState) -> dict:
    return {
        "session_id": state.get("session_id", ""),
        "session_name": state.get("session_name", ""),
        "output_path": state.get("output_path", ""),
        "product_name": "",  # extracted from spec if needed
    }


@node_trace("notify")
def notify(state: TheoryCraftState) -> dict:
    """Send Slack and/or generic webhook notifications. Non-blocking."""
    from theorycraft.config import get_settings
    cfg = get_settings()
    payload = _build_payload(state)
    results: list[NotificationResult] = []

    if cfg.slack_enabled:
        try:
            from theorycraft.integrations.slack import send_slack
            send_slack(cfg.slack_webhook_url, payload, output_path=state.get("output_path"))
            results.append(NotificationResult(channel="slack", success=True, error=None))
        except Exception as e:
            logger.warning("Slack notification failed: %s", e)
            results.append(NotificationResult(channel="slack", success=False, error=str(e)))

    if cfg.webhook_enabled:
        try:
            from theorycraft.integrations.webhook import send_webhook
            send_webhook(cfg.generic_webhook_url, payload)
            results.append(NotificationResult(channel="webhook", success=True, error=None))
        except Exception as e:
            logger.warning("Webhook notification failed: %s", e)
            results.append(NotificationResult(channel="webhook", success=False, error=str(e)))

    return {"notifications_sent": results}
