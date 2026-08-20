"""Tests for graph structure and state management."""
from __future__ import annotations

import pytest

from theorycraft.graph.state import TheoryCraftState, initial_state


def test_initial_state_defaults():
    state = initial_state(
        session_id="test-id",
        session_name="test-session",
        raw_idea="A todo app",
        output_dir="/tmp",
    )
    assert state["session_id"] == "test-id"
    assert state["raw_idea"] == "A todo app"
    assert state["clarifications"] == []
    assert state["concept_approved"] is False
    assert state["spec_approved"] is False
    assert state["clarify_round"] == 0
    assert state["revision_round"] == 0
    assert state["errors"] == []
    assert state["notifications_sent"] == []
    assert state["github_publish_mode"] == "repo"


def test_initial_state_with_options():
    state = initial_state(
        session_id="abc",
        session_name="my-app",
        raw_idea="Blog platform",
        output_dir="/out",
        max_clarify_rounds=1,
        max_revisions=2,
    )
    assert state["max_clarify_rounds"] == 1
    assert state["max_revisions"] == 2


def test_state_annotations():
    import operator
    from typing import Annotated, get_type_hints
    hints = get_type_hints(TheoryCraftState, include_extras=True)
    # clarifications uses operator.add reducer
    assert "clarifications" in hints
    assert "errors" in hints


def test_graph_builds():
    """Verify the graph compiles without errors."""
    from theorycraft.graph.builder import build_graph
    graph = build_graph(checkpointer=None)
    assert graph is not None


def test_graph_has_expected_nodes():
    from theorycraft.graph.builder import build_graph
    graph = build_graph(checkpointer=None)
    node_names = set(graph.nodes.keys())
    expected = {
        "intake", "clarify", "ideate", "service_design",
        "architecture", "api_design", "database_design",
        "backend_join", "frontend_design", "sdk_design", "frontend_join",
        "validate", "revise", "spec_compile", "github_publish", "notify",
    }
    # __start__ and __end__ are internal LangGraph nodes
    assert expected.issubset(node_names | {n.lstrip("_") for n in node_names})
