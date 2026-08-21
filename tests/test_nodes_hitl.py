"""Tests for HITL graph nodes (intake, clarify, ideate, validate)."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from theorycraft.graph.state import initial_state


def _state(**overrides) -> dict:
    s = dict(initial_state("test-id", "test-session", "A todo app", "/tmp"))
    s.update(overrides)
    return s


# ── intake ────────────────────────────────────────────────────────────────

class TestIntakeNode:
    def test_skips_interrupt_when_idea_already_set(self):
        from theorycraft.graph.nodes.intake import intake
        result = intake(_state(raw_idea="A todo app"))
        assert result == {}

    def test_collects_idea_via_interrupt(self):
        from theorycraft.graph.nodes.intake import intake
        with patch("theorycraft.graph.nodes.intake.interrupt", return_value="my great idea"):
            result = intake(_state(raw_idea=""))
        assert result["raw_idea"] == "my great idea"

    def test_collects_idea_from_dict_payload(self):
        from theorycraft.graph.nodes.intake import intake
        with patch("theorycraft.graph.nodes.intake.interrupt", return_value={"idea": "a cool app"}):
            result = intake(_state(raw_idea=""))
        assert result["raw_idea"] == "a cool app"


# ── clarify ───────────────────────────────────────────────────────────────

class TestClarifyNode:
    def test_creates_pair_from_string_answer(self):
        from theorycraft.graph.nodes.clarify import clarify
        with patch("theorycraft.graph.nodes.clarify.simple_call", return_value="1. Who are users?\n2. What platform?"):
            with patch("theorycraft.graph.nodes.clarify.interrupt", return_value="1. devs\n2. web"):
                result = clarify(_state())

        assert result["clarify_round"] == 1
        assert result["needs_more_clarification"] is False
        assert len(result["clarifications"]) == 1
        pair = result["clarifications"][0]
        assert "Who are users?" in pair["question"]
        assert "1. devs" in pair["answer"]

    def test_increments_clarify_round(self):
        from theorycraft.graph.nodes.clarify import clarify
        with patch("theorycraft.graph.nodes.clarify.simple_call", return_value="1. Q?"):
            with patch("theorycraft.graph.nodes.clarify.interrupt", return_value="answer"):
                result = clarify(_state(clarify_round=1))
        assert result["clarify_round"] == 2

    def test_accepts_list_of_pairs(self):
        from theorycraft.graph.nodes.clarify import clarify
        pairs = [("Who?", "devs"), ("What?", "web")]
        with patch("theorycraft.graph.nodes.clarify.simple_call", return_value="1. Who?\n2. What?"):
            with patch("theorycraft.graph.nodes.clarify.interrupt", return_value=pairs):
                result = clarify(_state())
        assert len(result["clarifications"]) == 2
        assert result["clarifications"][0]["question"] == "Who?"
        assert result["clarifications"][1]["answer"] == "web"

    def test_accept_dict_with_pairs_key(self):
        from theorycraft.graph.nodes.clarify import clarify
        from theorycraft.graph.state import ClarificationPair
        pair = ClarificationPair(question="Who?", answer="devs")
        payload = {"pairs": [pair]}
        with patch("theorycraft.graph.nodes.clarify.simple_call", return_value="1. Who?"):
            with patch("theorycraft.graph.nodes.clarify.interrupt", return_value=payload):
                result = clarify(_state())
        assert result["clarifications"][0]["question"] == "Who?"


# ── ideate ────────────────────────────────────────────────────────────────

class TestIdeateNode:
    def test_ready_signal_approves_concept(self):
        from theorycraft.graph.nodes.ideate import ideate
        with patch("theorycraft.graph.nodes.ideate.simple_call", return_value="Great concept"):
            with patch("theorycraft.graph.nodes.ideate.interrupt", return_value="/ready"):
                result = ideate(_state())
        assert result["concept_approved"] is True
        assert result["concept_summary"] == "Great concept"

    def test_go_alias_approves_concept(self):
        from theorycraft.graph.nodes.ideate import ideate
        with patch("theorycraft.graph.nodes.ideate.simple_call", return_value="Great concept"):
            with patch("theorycraft.graph.nodes.ideate.interrupt", return_value="go"):
                result = ideate(_state())
        assert result["concept_approved"] is True

    def test_clarify_signal_sets_needs_more_clarification(self):
        from theorycraft.graph.nodes.ideate import ideate
        with patch("theorycraft.graph.nodes.ideate.simple_call", return_value="Concept"):
            with patch("theorycraft.graph.nodes.ideate.interrupt", return_value="/clarify"):
                result = ideate(_state())
        assert result["concept_approved"] is False
        assert result["needs_more_clarification"] is True

    def test_feedback_loops_without_approval(self):
        from theorycraft.graph.nodes.ideate import ideate
        with patch("theorycraft.graph.nodes.ideate.simple_call", return_value="Concept"):
            with patch("theorycraft.graph.nodes.ideate.interrupt", return_value="make it simpler"):
                result = ideate(_state())
        assert result["concept_approved"] is False
        assert result["needs_more_clarification"] is False
        assert "make it simpler" in result["concept_summary"]

    def test_dict_input_with_input_key(self):
        from theorycraft.graph.nodes.ideate import ideate
        with patch("theorycraft.graph.nodes.ideate.simple_call", return_value="Concept"):
            with patch("theorycraft.graph.nodes.ideate.interrupt", return_value={"input": "/ready"}):
                result = ideate(_state())
        assert result["concept_approved"] is True

    def test_uses_refine_system_on_second_round(self):
        """Refinement path uses _REFINE_SYSTEM when ideation_rounds > 0 and concept exists."""
        from theorycraft.graph.nodes.ideate import ideate
        # ideation_rounds must be present and > 0 in state to trigger the refine branch
        state_with_rounds = {**_state(concept_summary="Old concept"), "ideation_rounds": 1}
        with patch("theorycraft.graph.nodes.ideate.simple_call", return_value="Refined concept") as mock_call:
            with patch("theorycraft.graph.nodes.ideate.interrupt", return_value="/ready"):
                result = ideate(state_with_rounds)
        assert result["concept_summary"] == "Refined concept"
        call_messages = mock_call.call_args[0][0]
        # Refine system starts with "continuing" context
        assert "continuing" in call_messages[0]["content"].lower()


# ── validate ──────────────────────────────────────────────────────────────

class TestValidateNode:
    def test_approve_sets_spec_approved(self):
        from theorycraft.graph.nodes.validate import validate
        with patch("theorycraft.graph.nodes.validate.interrupt", return_value="approve"):
            result = validate(_state())
        assert result == {"spec_approved": True}

    def test_yes_alias_approves(self):
        from theorycraft.graph.nodes.validate import validate
        with patch("theorycraft.graph.nodes.validate.interrupt", return_value="yes"):
            result = validate(_state())
        assert result["spec_approved"] is True

    def test_restart_clears_concept_approval(self):
        from theorycraft.graph.nodes.validate import validate
        with patch("theorycraft.graph.nodes.validate.interrupt", return_value="restart"):
            result = validate(_state(concept_approved=True))
        assert result["spec_approved"] is False
        assert result["concept_approved"] is False
        assert result["sections_to_revise"] == []

    def test_revise_command_parses_section_and_feedback(self):
        from theorycraft.graph.nodes.validate import validate
        with patch("theorycraft.graph.nodes.validate.interrupt", return_value="revise api_routes: add pagination"):
            result = validate(_state(revision_round=0))
        assert result["spec_approved"] is False
        assert result["revision_round"] == 1
        assert len(result["sections_to_revise"]) == 1
        req = result["sections_to_revise"][0]
        assert req["section"] == "api_routes"
        assert "pagination" in req["feedback"]

    def test_free_text_becomes_general_revision(self):
        from theorycraft.graph.nodes.validate import validate
        with patch("theorycraft.graph.nodes.validate.interrupt", return_value="the API needs rethinking"):
            result = validate(_state(revision_round=0))
        assert result["sections_to_revise"][0]["section"] == "general"
        assert "rethinking" in result["sections_to_revise"][0]["feedback"]

    def test_revision_round_increments(self):
        from theorycraft.graph.nodes.validate import validate
        with patch("theorycraft.graph.nodes.validate.interrupt", return_value="revise sdk: add auth helpers"):
            result = validate(_state(revision_round=1))
        assert result["revision_round"] == 2
        assert result["sections_to_revise"][0]["round"] == 2

    def test_summary_includes_services(self):
        """Verify _build_summary reflects state correctly (used in interrupt payload)."""
        from theorycraft.graph.nodes.validate import _build_summary
        s = _state(
            services_draft=[{"name": "api"}, {"name": "worker"}],
            api_routes_draft=[{"method": "GET", "path": "/users"}],
        )
        summary = _build_summary(s)
        assert "services (2)" in summary
        assert "api_routes (1)" in summary
