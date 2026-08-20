from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_langfuse_client: Optional[Any] = None


def _get_client() -> Optional[Any]:
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    try:
        from theorycraft.config import get_settings
        cfg = get_settings()
        if not cfg.langfuse_enabled:
            return None

        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=cfg.langfuse_public_key,
            secret_key=cfg.langfuse_secret_key,
            host=cfg.langfuse_host,
        )
        return _langfuse_client
    except Exception as e:
        logger.debug("Langfuse init skipped: %s", e)
        return None


def setup_litellm_callback() -> None:
    """Register Langfuse as a LiteLLM success_callback.

    Langfuse v4 dropped LangfuseCallback. LiteLLM has a built-in
    Langfuse integration activated by adding "langfuse" to success_callback;
    it reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY automatically.
    """
    client = _get_client()
    if client is None:
        return
    try:
        import litellm
        if "langfuse" not in (litellm.success_callback or []):
            litellm.success_callback = [*(litellm.success_callback or []), "langfuse"]
    except Exception as e:
        logger.debug("LiteLLM Langfuse callback skipped: %s", e)


def _sanitize_state(state: dict) -> dict:
    """Strip large SQL/blob fields from state before sending to Langfuse."""
    skip = {"raw_sql", "db_schema_draft"}
    return {k: v for k, v in state.items() if k not in skip and not isinstance(v, bytes)}


def _state_diff(before: dict, after: dict) -> dict:
    return {k: v for k, v in after.items() if before.get(k) != v}


def node_trace(node_name: str) -> Callable:
    """Decorator that wraps a LangGraph node with a Langfuse v4 observation span.

    Uses start_as_current_observation() — the v4 context-manager API.
    If Langfuse is not configured the node runs unchanged.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(state: dict, *args: Any, **kwargs: Any) -> Any:
            client = _get_client()
            if client is None:
                return fn(state, *args, **kwargs)

            session_id = state.get("session_id", "unknown")

            try:
                from langfuse.types import TraceContext
                # Langfuse v4 requires a 32 lowercase hex char trace ID.
                # UUID4 session IDs are already hex — just strip the dashes.
                hex_id = session_id.replace("-", "").lower()[:32].ljust(32, "0")
                trace_context = TraceContext(trace_id=hex_id)
            except Exception:
                trace_context = None

            cm_kwargs: dict = dict(
                name=node_name,
                as_type="agent",
                input=_sanitize_state(state),
                metadata={"session_id": session_id},
            )
            if trace_context is not None:
                cm_kwargs["trace_context"] = trace_context

            try:
                with client.start_as_current_observation(**cm_kwargs):
                    result = fn(state, *args, **kwargs)
                    diff = _state_diff(state, result) if isinstance(result, dict) else {}
                    try:
                        client.update_current_span(output=diff)
                    except Exception:
                        pass
                    return result
            except Exception as exc:
                raise

        return wrapper
    return decorator


def flush() -> None:
    """Flush pending Langfuse events — call before process exit."""
    client = _get_client()
    if client:
        try:
            client.shutdown()
        except Exception:
            try:
                client.flush()
            except Exception:
                pass
