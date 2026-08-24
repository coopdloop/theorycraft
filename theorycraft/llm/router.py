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

# Drop params the model doesn't support (e.g. temperature on newer Claude models)
litellm.drop_params = True

# ── Token tracking ────────────────────────────────────────────────────────────

_token_lock = threading.Lock()
_total_tokens: int = 0


def add_tokens(n: int) -> None:
    global _total_tokens
    with _token_lock:
        _total_tokens = max(0, _total_tokens + n)


def get_total_tokens() -> int:
    with _token_lock:
        return _total_tokens


def reset_tokens() -> None:
    global _total_tokens
    with _token_lock:
        _total_tokens = 0


# ── LLM client ───────────────────────────────────────────────────────────────

def _get_instructor() -> Any:
    global _instructor_client
    if _instructor_client is None:
        setup_litellm_callback()
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


# ── Call functions ────────────────────────────────────────────────────────────

def structured_call(
    response_model: Type[T],
    messages: list[dict],
    *,
    model: Optional[str] = None,
    max_retries: int = 3,
    temperature: float = 0.2,
    **kwargs: Any,
) -> T:
    """Instructor structured output. Uses create_with_completion to capture usage."""
    client = _get_instructor()
    target_model = model or get_model()
    _log_call(target_model, messages, temperature, "structured")

    result, completion = client.chat.completions.create_with_completion(
        model=target_model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
        temperature=temperature,
        **kwargs,
    )

    usage = getattr(completion, "usage", None)
    if usage:
        tokens = getattr(usage, "total_tokens", 0) or 0
        if tokens:
            add_tokens(tokens)

    logger.info("llm.response  structured=%s", type(result).__name__)
    return result


def stream_call(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.7,
    **kwargs: Any,
) -> Any:
    """Raw streaming generator. Callers consume the stream directly."""
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
    """Stream internally, drip token estimates per-chunk, correct on completion."""
    target_model = model or get_model()
    _log_call(target_model, messages, temperature, "simple")

    stream = litellm.completion(
        model=target_model,
        messages=messages,
        temperature=temperature,
        stream=True,
        **kwargs,
    )

    parts: list[str] = []
    estimated: int = 0
    final_usage: Any = None

    for chunk in stream:
        delta = (
            chunk.choices[0].delta.content
            if chunk.choices and chunk.choices[0].delta.content
            else None
        )
        if delta:
            parts.append(delta)
            est = max(1, len(delta) // 4)
            estimated += est
            add_tokens(est)

        chunk_usage = getattr(chunk, "usage", None)
        if chunk_usage and getattr(chunk_usage, "total_tokens", 0):
            final_usage = chunk_usage

    content = "".join(parts)

    # Correct the running estimate with the real total (adds input tokens + fixes drift)
    if final_usage:
        real = getattr(final_usage, "total_tokens", 0) or 0
        if real > 0:
            add_tokens(real - estimated)

    _log_response(content, final_usage)
    return content
