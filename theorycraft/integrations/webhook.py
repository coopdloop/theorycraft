from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def send_webhook(url: str, payload: dict, *, timeout: int = 10) -> None:
    """POST payload to a generic HTTP webhook endpoint."""
    resp = httpx.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    logger.info("Webhook notification sent to %s (status %s)", url, resp.status_code)
