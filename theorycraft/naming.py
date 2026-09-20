"""Name generation shared by sessions, specs, and GitHub repos.

Repo names used to be ``slugify(raw_idea)[:40] + "-spec"``, which produced
names like ``a-llm-cli-chat-where-you-talk-with-and-i-spec`` — a truncated
mid-word sentence rather than the product's actual name. Names are now derived
from the spec's product name and always truncated on word boundaries.
"""

from __future__ import annotations

import re

from slugify import slugify as _slugify

# GitHub rejects repo names longer than this.
GITHUB_REPO_MAX_LENGTH = 100
# Kept short enough to read in `ls` and terminal output.
SESSION_MAX_LENGTH = 48
DEFAULT_REPO_SUFFIX = "-spec"

# Leading filler from "I want to build an app that…" style prompts.
_PROMPT_FILLER = frozenset({
    "a", "an", "the", "i", "im", "is", "my", "our", "we", "you", "your",
    "to", "for", "of", "with", "and", "that", "this", "it",
    "build", "create", "make", "want", "need", "please", "like",
})


def slugify_words(text: str, max_length: int = SESSION_MAX_LENGTH) -> str:
    """Slugify ``text``, dropping trailing words instead of cutting one in half."""
    full = _slugify(text).strip("-")
    if not full or len(full) <= max_length:
        return full

    kept: list[str] = []
    length = 0
    for word in full.split("-"):
        extra = len(word) + (1 if kept else 0)
        if length + extra > max_length:
            break
        kept.append(word)
        length += extra

    # Even the first word overflows the budget — hard-cut as a last resort.
    return "-".join(kept) or full[:max_length].strip("-")


def idea_slug(text: str, max_length: int = SESSION_MAX_LENGTH) -> str:
    """Slugify a raw product idea for use as a session or directory name."""
    words = _slugify(text).strip("-").split("-")
    while words and words[0] in _PROMPT_FILLER:
        words.pop(0)

    slug = slugify_words("-".join(words), max_length)

    # Word-boundary truncation can leave a dangling conjunction — "…talk-with-and".
    parts = slug.split("-")
    while len(parts) > 1 and parts[-1] in _PROMPT_FILLER:
        parts.pop()
    return "-".join(parts)


def repo_name(product_name: str = "", session_name: str = "", *, suffix: str = DEFAULT_REPO_SUFFIX) -> str:
    """Name a spec repo after the product, falling back to the session slug.

    The base is truncated to leave room for ``suffix``, so the suffix is never
    cut off and the result always fits GitHub's limit.
    """
    budget = max(1, GITHUB_REPO_MAX_LENGTH - len(suffix))
    base = slugify_words(product_name, budget) or idea_slug(session_name, budget) or "theorycraft"

    stem = suffix.strip("-")
    if base == stem or base.endswith(f"-{stem}"):
        return base  # don't produce "paerhaps-spec-spec"
    return f"{base}{suffix}"


def package_scope(name: str, max_length: int = 40) -> str:
    """npm package scope, e.g. ``paerhaps`` for ``@paerhaps/client``."""
    return slugify_words(name, max_length) or "myproduct"


_PRODUCT_NAME_PATTERNS = (
    re.compile(r"^#+\s*product\s+name\s*[:\-—]\s*(?P<name>.+)$", re.I | re.M),
    re.compile(r"^\**\s*product\s+name\s*[:\-—]\s*\**\s*(?P<name>.+?)\**\s*$", re.I | re.M),
    re.compile(r"\*\*product\s+name\*\*\s*[:\-—]?\s*(?P<name>[^\n]+)", re.I),
)


def product_name_from_concept(concept: str, max_length: int = 40) -> str:
    """Pull the product name out of an ideation summary, wherever the model wrote it.

    The concept is free-form markdown, so the name shows up as a heading, a bolded
    label, or a ``**Product name**:`` line depending on mood. Falls back to the
    first line so callers always get something better than a truncated sentence.
    """
    for pattern in _PRODUCT_NAME_PATTERNS:
        match = pattern.search(concept or "")
        if match:
            candidate = re.sub(r"[*`#]", "", match.group("name")).strip(" :-—")
            candidate = re.split(r"\s+[—–]|\n", candidate)[0].strip()
            if candidate:
                return _clip_words(candidate, max_length)
    return title_from_concept(concept or "", max_length=max_length)


def _clip_words(text: str, max_length: int) -> str:
    words: list[str] = []
    length = 0
    for word in text.split():
        if words and length + len(word) + 1 > max_length:
            break
        words.append(word)
        length += len(word) + 1
    return " ".join(words).rstrip(" -:")


def title_from_concept(concept: str, max_length: int = 60) -> str:
    """Best-effort product name from the first line of a concept summary."""
    line = concept.strip().splitlines()[0] if concept.strip() else ""
    line = re.sub(r"^#+\s*", "", line)
    line = re.sub(r"^\W*(product name|name)\W*", "", line, flags=re.I)
    line = re.sub(r"[*\u2013\u2014`]", "", line).strip(" :-\u2014")
    return _clip_words(line, max_length) or "Untitled product"
