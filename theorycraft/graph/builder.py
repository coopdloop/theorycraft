from __future__ import annotations

from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from theorycraft.graph.nodes import (
    api_design,
    architecture,
    clarify,
    database_design,
    frontend_design,
    github_publish,
    ideate,
    intake,
    notify,
    revise,
    sdk_design,
    service_design,
    spec_compile,
    validate,
)
from theorycraft.graph.state import TheoryCraftState


# ── Conditional edge routers ──────────────────────────────────────────────

def _after_intake(state: TheoryCraftState) -> str:
    clarifications = state.get("clarifications", [])
    if not clarifications and state.get("max_clarify_rounds", 0) > 0:
        return "clarify"
    return "ideate"


def _after_clarify(state: TheoryCraftState) -> str:
    return "ideate"


def _after_ideate(state: TheoryCraftState) -> str:
    if state.get("needs_more_clarification"):
        return "clarify"
    if state.get("concept_approved"):
        return "service_design"
    return "ideate"


def _after_service_design(state: TheoryCraftState) -> list[str]:
    """Fan out to architecture, api_design, database_design in parallel."""
    return ["architecture", "api_design", "database_design"]


def _after_parallel_backend(state: TheoryCraftState) -> list[str]:
    """After all backend design nodes complete, fan to frontend + sdk in parallel."""
    return ["frontend_design", "sdk_design"]


def _all_backend_complete(state: TheoryCraftState) -> str:
    """Check if all backend design outputs are present."""
    if (
        state.get("architecture_draft") is not None
        and state.get("api_routes_draft") is not None
        and state.get("db_schema_draft") is not None
    ):
        return "fan_to_frontend"
    return "wait"


def _after_validate(state: TheoryCraftState) -> str:
    if state.get("spec_approved"):
        return "spec_compile"
    if not state.get("concept_approved"):
        return "ideate"
    revision_round = state.get("revision_round", 0)
    max_revisions = state.get("max_revisions", 3)
    if revision_round >= max_revisions:
        return "spec_compile"
    if state.get("sections_to_revise"):
        return "revise"
    return "spec_compile"


def _after_revise(state: TheoryCraftState) -> str:
    return "validate"


def _after_spec_compile(state: TheoryCraftState) -> str:
    from theorycraft.config import get_settings
    cfg = get_settings()
    if cfg.github_enabled:
        return "github_publish"
    if cfg.slack_enabled or cfg.webhook_enabled:
        return "notify"
    return END


def _after_github_publish(state: TheoryCraftState) -> str:
    from theorycraft.config import get_settings
    cfg = get_settings()
    if cfg.slack_enabled or cfg.webhook_enabled:
        return "notify"
    return END


# ── Aggregator node — waits for all backend nodes before continuing ───────

def _backend_join(state: TheoryCraftState) -> dict:
    """No-op aggregator. LangGraph calls this after all Send() targets complete."""
    return {}


def _frontend_join(state: TheoryCraftState) -> dict:
    """No-op aggregator after frontend + sdk parallel nodes."""
    return {}


# ── Graph construction ────────────────────────────────────────────────────

def build_graph(checkpointer: Any = None) -> Any:
    """Build and compile the theorycraft StateGraph."""
    graph = StateGraph(TheoryCraftState)

    # Nodes
    graph.add_node("intake", intake)
    graph.add_node("clarify", clarify)
    graph.add_node("ideate", ideate)
    graph.add_node("service_design", service_design)
    graph.add_node("architecture", architecture)
    graph.add_node("api_design", api_design)
    graph.add_node("database_design", database_design)
    graph.add_node("backend_join", _backend_join)
    graph.add_node("frontend_design", frontend_design)
    graph.add_node("sdk_design", sdk_design)
    graph.add_node("frontend_join", _frontend_join)
    graph.add_node("validate", validate)
    graph.add_node("revise", revise)
    graph.add_node("spec_compile", spec_compile)
    graph.add_node("github_publish", github_publish)
    graph.add_node("notify", notify)

    # Edges: intake → clarify/ideate
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", _after_intake, {"clarify": "clarify", "ideate": "ideate"})
    graph.add_conditional_edges("clarify", _after_clarify, {"ideate": "ideate"})

    # Edges: ideate loop + fan-out to service_design
    graph.add_conditional_edges(
        "ideate",
        _after_ideate,
        {
            "clarify": "clarify",
            "service_design": "service_design",
            "ideate": "ideate",
        },
    )

    # service_design → parallel backend nodes
    graph.add_edge("service_design", "architecture")
    graph.add_edge("service_design", "api_design")
    graph.add_edge("service_design", "database_design")

    # All three backend nodes converge at backend_join
    graph.add_edge("architecture", "backend_join")
    graph.add_edge("api_design", "backend_join")
    graph.add_edge("database_design", "backend_join")

    # backend_join → parallel frontend nodes
    graph.add_edge("backend_join", "frontend_design")
    graph.add_edge("backend_join", "sdk_design")

    # frontend + sdk converge at frontend_join
    graph.add_edge("frontend_design", "frontend_join")
    graph.add_edge("sdk_design", "frontend_join")

    # frontend_join → validate
    graph.add_edge("frontend_join", "validate")

    # validate routes
    graph.add_conditional_edges(
        "validate",
        _after_validate,
        {
            "spec_compile": "spec_compile",
            "ideate": "ideate",
            "revise": "revise",
        },
    )
    graph.add_conditional_edges("revise", _after_revise, {"validate": "validate"})

    # spec_compile → github_publish / notify / END
    graph.add_conditional_edges(
        "spec_compile",
        _after_spec_compile,
        {
            "github_publish": "github_publish",
            "notify": "notify",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "github_publish",
        _after_github_publish,
        {
            "notify": "notify",
            END: END,
        },
    )
    graph.add_edge("notify", END)

    return graph.compile(checkpointer=checkpointer)


class GraphSession:
    """Context manager that owns the SQLite checkpointer lifetime."""

    def __init__(self, session_db_path: str) -> None:
        self._path = session_db_path
        self._cm: Any = None   # the contextmanager returned by from_conn_string
        self._saver: Any = None  # the actual BaseCheckpointSaver from __enter__
        self.graph: Any = None

    def __enter__(self) -> "GraphSession":
        # from_conn_string returns a _GeneratorContextManager, not a saver.
        # Calling __enter__() on it yields the real SqliteSaver instance.
        self._cm = SqliteSaver.from_conn_string(self._path)
        self._saver = self._cm.__enter__()
        self.graph = build_graph(self._saver)
        return self

    def __exit__(self, *args: Any) -> None:
        if self._cm:
            self._cm.__exit__(*args)
