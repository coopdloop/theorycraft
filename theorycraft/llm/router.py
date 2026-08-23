from __future__ import annotations

import logging
import threading
from typing import Any, Optional, Type, TypeVar

import instructor
import litellm

from theorycraft.config import get_settings
from theorycraft.telemetry.langfuse import setup_litellm_callback

logger = logging.getLogger(__name__)

T = TypeVar("T")

_instructor_client: Optional[Any] = None
_callbacks_registered: bool = False

# Drop params the model doesn't support (e.g. temperature on newer Claude models)
# rather than raising UnsupportedParamsError.
litellm.drop_params = True

# ── Token tracking ────────────────────────────────────────────────────────

_token_lock = threading.Lock()
_total_tokens: int = 0


def add_tokens(n: int) -> None:
    global _total_tokens
    with _token_lock:
        _total_tokens += n


def get_total_tokens() -> int:
    with _token_lock:
        return _total_tokens


def reset_tokens() -> None:
    global _total_tokens
    with _token_lock:
        _total_tokens = 0


def _track_tokens(kwargs: Any, completion_response: Any, start_time: Any, end_time: Any) -> None:
    usage = getattr(completion_response, "usage", None)
    if usage:
        n = getattr(usage, "total_tokens", 0) or 0
        if n:
            add_tokens(n)


def _get_instructor() -> Any:
    global _instructor_client, _callbacks_registered
    if _instructor_client is None:
        setup_litellm_callback()
        if not _callbacks_registered:
            litellm.success_callback = list(litellm.success_callback) + [_track_tokens]
            _callbacks_registered = True
        _instructor_client = instructor.from_litellm(litellm.completion)
    return _instructor_client


def get_model() -> str:
    return get_settings().model


def _log_call(model: str, messages: list[dict], temperature: float, kind: str) -> None:
    last = messages[-1].get("content", "") if messages else ""
    preview = str(last)[:100].replace("\n", " ")
    logger.info("%-10s  %s  (%d msgs, temp=%.1f)  %r", kind, model, len(messages), temperature, preview)


def _log_response(content: str, usage: Any) -> None:
    tokens = getattr(usage, "total_tokens", None) if usage else None
    tok = f"{tokens} tok" if tokens else "? tok"
    preview = content[:100].replace("\n", " ")
    logger.info("%-10s  %d chars  %s  %r", "←", len(content), tok, preview)


def structured_call(
    response_model: Type[T],
    messages: list[dict],
    *,
    model: Optional[str] = None,
    max_retries: int = 3,
    temperature: float = 0.2,
    **kwargs: Any,
) -> T:
    """Call LiteLLM with instructor structured output. Deterministic nodes use this."""
    client = _get_instructor()
    target_model = model or get_model()
    _log_call(target_model, messages, temperature, "structured")
    result = client.chat.completions.create(
        model=target_model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
        temperature=temperature,
        **kwargs,
    )
    logger.info("llm.response  structured=%s", type(result).__name__)
    return result


def stream_call(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.7,
    **kwargs: Any,
) -> Any:
    """Call LiteLLM with streaming. Creative nodes use this."""
    target_model = model or get_model()
    _log_call(target_model, messages, temperature, "stream")
    return litellm.completion(
        model=target_model,
        messages=messages,
        stream=True,
        temperature=temperature,
        **kwargs,
    )


def simple_call(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.5,
    **kwargs: Any,
) -> str:
    """Non-streaming call returning just the text content."""
    target_model = model or get_model()
    _log_call(target_model, messages, temperature, "simple")
    resp = litellm.completion(
        model=target_model,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )
    content = resp.choices[0].message.content or ""
    _log_response(content, getattr(resp, "usage", None))
    return content
