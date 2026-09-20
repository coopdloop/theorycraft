from __future__ import annotations

import json
import logging
from pathlib import Path

from theorycraft.graph.state import TheoryCraftState
from theorycraft.telemetry.langfuse import node_trace

logger = logging.getLogger(__name__)


@node_trace("github_publish")
def github_publish(state: TheoryCraftState) -> dict:
    """Publish the product spec to GitHub (new repo, PR, or Gist)."""
    try:
        from theorycraft.config import get_settings
        from theorycraft.integrations.github import GitHubClient

        cfg = get_settings()
        if not cfg.github_enabled:
            return {"errors": ["GitHub not configured — skipping publish"]}

        output_path = state.get("output_path")
        if not output_path:
            return {"errors": ["No output_path in state — spec_compile must run first"]}

        content = Path(output_path).read_text()
        client = GitHubClient(cfg)
        session_name = state.get("session_name", "theorycraft-spec")
        product_name = _product_name(content) or (state.get("product_name") or "").strip()

        # Determine publish mode from state (can be passed via CLI)
        publish_mode = state.get("github_publish_mode", "repo")

        if publish_mode == "gist":
            url = client.create_gist(product_name or session_name, content)
        elif publish_mode == "pr":
            existing_repo = state.get("github_existing_repo", "")
            url = client.create_pr(existing_repo, session_name, content, product_name)
        else:
            url = client.create_repo(session_name, content, org=cfg.github_org, product_name=product_name)

        return {"github_output_url": url}

    except Exception as exc:
        logger.warning("GitHub publish failed: %s", exc)
        return {"errors": [f"GitHub publish failed: {exc}"]}


def _product_name(spec_content: str) -> str:
    """Pull vision.name out of the compiled product.json so repos get real names."""
    try:
        vision = json.loads(spec_content).get("vision") or {}
    except (ValueError, AttributeError):
        return ""
    return str(vision.get("name") or "").strip()
