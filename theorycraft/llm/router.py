from __future__ import annotations

import logging
from typing import Any, Optional, Type, TypeVar

import instructor
import litellm

from theorycraft.config import get_settings
from theorycraft.telemetry.langfuse import setup_litellm_callback

logger = logging.getLogger(__name__)

T = TypeVar("T")

_instructor_client: Optional[Any] = None

# Drop params the model doesn't support (e.g. temperature on newer Claude models)
# rather than raising UnsupportedParamsError.
litellm.drop_params = True


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
    preview = str(last)[:120].replace("\n", " ")
    logger.info("llm.%-10s  model=%-32s  msgs=%d  temp=%.1f  → %r", kind, model, len(messages), temperature, preview)


def _log_response(content: str, usage: Any) -> None:
    tokens = getattr(usage, "total_tokens", None) if usage else None
    token_str = f"~{tokens} tok" if tokens else ""
    preview = content[:120].replace("\n", " ")
    logger.info("llm.response  %d chars  %s  %r", len(content), token_str, preview)


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
