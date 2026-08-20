from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def send_slack(webhook_url: str, payload: dict, *, output_path: Optional[str] = None) -> None:
    """Post a spec-complete notification to a Slack incoming webhook."""
    session_name = payload.get("session_name", "unknown")
    product_name = payload.get("product_name") or session_name

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":sparkles: Product spec ready: {product_name}"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Session:*\n`{session_name}`"},
                {"type": "mrkdwn", "text": f"*Output:*\n`{output_path or 'N/A'}`"},
            ],
        },
    ]

    if output_path and Path(output_path).exists():
        try:
            spec = json.loads(Path(output_path).read_text())
            vision = spec.get("vision", {})
            tagline = vision.get("tagline", "")
            services = len(spec.get("services", []))
            routes = len(spec.get("api_routes", []))
            if tagline:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"_{tagline}_\n\n*{services} services* · *{routes} API routes*"},
                })
        except Exception:
            pass

    resp = httpx.post(webhook_url, json={"blocks": blocks}, timeout=10)
    resp.raise_for_status()
    logger.info("Slack notification sent")
