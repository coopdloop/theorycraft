"""Tests for graph conditional edge routing logic."""
from __future__ import annotations

import pytest

from theorycraft.graph.builder import (
    _after_clarify,
    _after_github_publish,
    _after_ideate,
    _after_intake,
    _after_revise,
    _after_spec_compile,
    _after_validate,
)
from theorycraft.graph.state import initial_state


def _state(**overrides) -> dict:
    s = dict(initial_state("test-id", "test-session", "A todo app", "/tmp"))
    s.update(overrides)
    return s


class TestAfterIntake:
    def test_goes_to_clarify_when_no_clarifications(self):
        assert _after_intake(_state(clarifications=[], max_clarify_rounds=2)) == "clarify"

    def test_goes_to_ideate_when_clarifications_already_exist(self):
        s = _state(
            clarifications=[{"question": "q", "answer": "a"}],
            max_clarify_rounds=2,
        )
        assert _after_intake(s) == "ideate"

    def test_goes_to_ideate_when_max_rounds_is_zero(self):
        assert _after_intake(_state(clarifications=[], max_clarify_rounds=0)) == "ideate"


class TestAfterClarify:
    def test_always_goes_to_ideate(self):
        assert _after_clarify(_state()) == "ideate"


class TestAfterIdeate:
    def test_goes_to_clarify_when_needs_more(self):
        assert _after_ideate(_state(needs_more_clarification=True)) == "clarify"

    def test_goes_to_service_design_when_approved(self):
        assert _after_ideate(_state(concept_approved=True)) == "service_design"

    def test_loops_when_not_approved_and_no_clarification_needed(self):
        assert _after_ideate(_state(concept_approved=False, needs_more_clarification=False)) == "ideate"

    def test_clarify_takes_priority_over_approved(self):
        # needs_more_clarification is checked first
        assert _after_ideate(_state(concept_approved=True, needs_more_clarification=True)) == "clarify"


class TestAfterValidate:
    def test_approved_goes_to_spec_compile(self):
        assert _after_validate(_state(spec_approved=True)) == "spec_compile"

    def test_concept_not_approved_goes_to_ideate(self):
        assert _after_validate(_state(spec_approved=False, concept_approved=False)) == "ideate"

    def test_with_sections_goes_to_revise(self):
        s = _state(
            spec_approved=False,
            concept_approved=True,
            revision_round=1,
            max_revisions=3,
            sections_to_revise=[{"section": "api_routes", "feedback": "add pagination", "round": 1}],
        )
        assert _after_validate(s) == "revise"

    def test_max_revisions_reached_goes_to_spec_compile(self):
        s = _state(
            spec_approved=False,
            concept_approved=True,
            revision_round=3,
            max_revisions=3,
            sections_to_revise=[{"section": "api_routes", "feedback": "add pagination", "round": 3}],
        )
        assert _after_validate(s) == "spec_compile"

    def test_no_sections_with_approved_concept_goes_to_spec_compile(self):
        s = _state(
            spec_approved=False,
            concept_approved=True,
            sections_to_revise=[],
            revision_round=0,
            max_revisions=3,
        )
        assert _after_validate(s) == "spec_compile"


class TestAfterRevise:
    def test_always_goes_to_validate(self):
        assert _after_revise(_state()) == "validate"


class TestAfterSpecCompile:
    def test_github_enabled_goes_to_github_publish(self, monkeypatch):
        _mock_settings(monkeypatch, github_enabled=True, slack_enabled=False, webhook_enabled=False)
        assert _after_spec_compile(_state()) == "github_publish"

    def test_slack_enabled_goes_to_notify(self, monkeypatch):
        _mock_settings(monkeypatch, github_enabled=False, slack_enabled=True, webhook_enabled=False)
        assert _after_spec_compile(_state()) == "notify"

    def test_webhook_enabled_goes_to_notify(self, monkeypatch):
        _mock_settings(monkeypatch, github_enabled=False, slack_enabled=False, webhook_enabled=True)
        assert _after_spec_compile(_state()) == "notify"

    def test_nothing_enabled_goes_to_end(self, monkeypatch):
        from langgraph.graph import END
        _mock_settings(monkeypatch, github_enabled=False, slack_enabled=False, webhook_enabled=False)
        assert _after_spec_compile(_state()) == END


class TestAfterGithubPublish:
    def test_slack_enabled_goes_to_notify(self, monkeypatch):
        _mock_settings(monkeypatch, github_enabled=True, slack_enabled=True, webhook_enabled=False)
        assert _after_github_publish(_state()) == "notify"

    def test_nothing_enabled_goes_to_end(self, monkeypatch):
        from langgraph.graph import END
        _mock_settings(monkeypatch, github_enabled=False, slack_enabled=False, webhook_enabled=False)
        assert _after_github_publish(_state()) == END


# ── Helper ────────────────────────────────────────────────────────────────

def _mock_settings(monkeypatch, **flags):
    class _Cfg:
        pass
    for k, v in flags.items():
        setattr(_Cfg, k, v)
    monkeypatch.setattr("theorycraft.config.get_settings", lambda: _Cfg())
