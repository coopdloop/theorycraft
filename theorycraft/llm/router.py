from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable, Optional, Type, TypeVar

import instructor
import litellm

from theorycraft.config import get_settings
from theorycraft.telemetry.langfuse import setup_litellm_callback

logger = logging.getLogger(__name__)

T = TypeVar("T")

_instructor_client: Optional[Any] = None

# Drop params the model doesn't support (e.g. temperature on newer Claude models)
litellm.drop_params = True

# ── Retry / backoff ────────────────────────────────────────────────────────────

# Transient errors worth retrying with exponential backoff.
_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    litellm.RateLimitError,
    litellm.APIConnectionError,
    litellm.ServiceUnavailableError,
    litellm.InternalServerError,
    litellm.Timeout,
)

_MAX_ATTEMPTS = 8
_BASE_DELAY = 2.0
_MAX_DELAY = 60.0


def _retry_after_seconds(exc: Exception) -> Optional[float]:
    """Extract a Retry-After hint from the provider response, if present."""
    headers = getattr(exc, "response", None)
    headers = getattr(headers, "headers", None) or getattr(exc, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _with_retries(fn: Callable[[], T], *, kind: str) -> T:
    """Run fn with exponential backoff + jitter on transient LLM errors."""
    attempt = 0
    while True:
        try:
            return fn()
        except _RETRYABLE_EXCEPTIONS as exc:
            attempt += 1
            if attempt >= _MAX_ATTEMPTS:
                logger.error("%s call failed after %d attempts: %s", kind, attempt, exc)
                raise
            hinted = _retry_after_seconds(exc)
            backoff = min(_MAX_DELAY, _BASE_DELAY * (2 ** (attempt - 1)))
            delay = hinted if hinted is not None else backoff
            delay += random.uniform(0, min(1.0, delay))
            logger.warning(
                "%s call hit %s (attempt %d/%d); retrying in %.1fs",
                kind, type(exc).__name__, attempt, _MAX_ATTEMPTS, delay,
            )
            time.sleep(delay)


def _stream_with_retries(stream_factory: Callable[[], Any], *, kind: str) -> Any:
    """Wrap a streaming generator factory with retry logic.
    
    Returns a generator that retries on first-chunk failures.
    Mid-stream failures after the first chunk are not retried (partial data already yielded).
    """
    attempt = 0
    while True:
        first_chunk = None
        try:
            stream = stream_factory()
            # Force the first chunk to fail fast if rate-limited
            for chunk in stream:
                if first_chunk is None:
                    first_chunk = chunk
                    yield chunk
                else:
                    yield chunk
            return
        except _RETRYABLE_EXCEPTIONS as exc:
            if first_chunk is not None:
                # Mid-stream failure after yielding data — don't retry, re-raise
                logger.error("%s stream failed mid-flight: %s", kind, exc)
                raise
            attempt += 1
            if attempt >= _MAX_ATTEMPTS:
                logger.error("%s stream failed after %d attempts: %s", kind, attempt, exc)
                raise
            hinted = _retry_after_seconds(exc)
            backoff = min(_MAX_DELAY, _BASE_DELAY * (2 ** (attempt - 1)))
            delay = hinted if hinted is not None else backoff
            delay += random.uniform(0, min(1.0, delay))
            logger.warning(
                "%s stream hit %s (attempt %d/%d); retrying in %.1fs",
                kind, type(exc).__name__, attempt, _MAX_ATTEMPTS, delay,
            )
            time.sleep(delay)

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

    creds = get_settings().llm_credentials
    result, completion = _with_retries(
        lambda: client.chat.completions.create_with_completion(
            model=target_model,
            messages=messages,
            response_model=response_model,
            max_retries=max_retries,
            temperature=temperature,
            **creds,
            **kwargs,
        ),
        kind="structured",
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
    creds = get_settings().llm_credentials
    return _stream_with_retries(
        lambda: litellm.completion(
            model=target_model,
            messages=messages,
            stream=True,
            temperature=temperature,
            **creds,
            **kwargs,
        ),
        kind="stream",
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

    creds = get_settings().llm_credentials
    stream = _stream_with_retries(
        lambda: litellm.completion(
            model=target_model,
            messages=messages,
            temperature=temperature,
            stream=True,
            **creds,
            **kwargs,
        ),
        kind="simple",
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
