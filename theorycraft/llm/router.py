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
    return client.chat.completions.create(
        model=target_model,
        messages=messages,
        response_model=response_model,
        max_retries=max_retries,
        temperature=temperature,
        **kwargs,
    )


def stream_call(
    messages: list[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.7,
    **kwargs: Any,
) -> Any:
    """Call LiteLLM with streaming. Creative nodes use this."""
    target_model = model or get_model()
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
    resp = litellm.completion(
        model=target_model,
        messages=messages,
        temperature=temperature,
        **kwargs,
    )
    return resp.choices[0].message.content or ""
