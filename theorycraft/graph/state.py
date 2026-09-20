from __future__ import annotations

import operator
from typing import Annotated, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from typing_extensions import TypedDict


class ClarificationPair(TypedDict):
    question: str
    answer: str


class RevisionRequest(TypedDict):
    section: str
    feedback: str
    round: int


class NotificationResult(TypedDict):
    channel: str
    success: bool
    error: Optional[str]


class TheoryCraftState(TypedDict):
    # ── Session ──────────────────────────────────────────────────────────
    session_id: str
    session_name: str

    # ── Messages (full conversation history) ─────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Raw input ─────────────────────────────────────────────────────────
    raw_idea: str
    additional_contexts: list[str]

    # ── Clarification ─────────────────────────────────────────────────────
    clarifications: Annotated[list[ClarificationPair], operator.add]
    clarify_round: int
    needs_more_clarification: bool

    # ── Concept ───────────────────────────────────────────────────────────
    concept_summary: str
    concept_approved: bool
    product_name: Optional[str]

    # ── Design drafts (set by respective nodes) ───────────────────────────
    services_draft: Optional[list[dict]]
    architecture_draft: Optional[dict]
    api_routes_draft: Optional[list[dict]]
    db_schema_draft: Optional[dict]
    frontend_draft: Optional[dict]
    sdk_draft: Optional[dict]

    # ── Validation ────────────────────────────────────────────────────────
    spec_approved: bool
    sections_to_revise: Annotated[list[RevisionRequest], operator.add]
    revision_round: int

    # ── Output ────────────────────────────────────────────────────────────
    output_path: Optional[str]

    # ── Integration outputs ───────────────────────────────────────────────
    github_output_url: Optional[str]
    github_publish_mode: str   # "repo" | "pr" | "gist"
    github_existing_repo: str  # for PR mode

    # ── Notifications ─────────────────────────────────────────────────────
    notifications_sent: Annotated[list[NotificationResult], operator.add]

    # ── Errors (non-fatal, accumulated) ──────────────────────────────────
    errors: Annotated[list[str], operator.add]

    # ── Config (read-only after init) ─────────────────────────────────────
    max_clarify_rounds: int
    max_revisions: int
    output_dir: str


def initial_state(
    session_id: str,
    session_name: str,
    raw_idea: str,
    output_dir: str,
    max_clarify_rounds: int = 2,
    max_revisions: int = 3,
) -> TheoryCraftState:
    return TheoryCraftState(
        session_id=session_id,
        session_name=session_name,
        messages=[],
        raw_idea=raw_idea,
        additional_contexts=[],
        clarifications=[],
        clarify_round=0,
        needs_more_clarification=False,
        concept_summary="",
        concept_approved=False,
        product_name="",
        services_draft=None,
        architecture_draft=None,
        api_routes_draft=None,
        db_schema_draft=None,
        frontend_draft=None,
        sdk_draft=None,
        spec_approved=False,
        sections_to_revise=[],
        revision_round=0,
        output_path=None,
        github_output_url=None,
        github_publish_mode="repo",
        github_existing_repo="",
        notifications_sent=[],
        errors=[],
        max_clarify_rounds=max_clarify_rounds,
        max_revisions=max_revisions,
        output_dir=output_dir,
    )
