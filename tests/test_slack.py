"""Tests for Slack session store and message formatter."""
from __future__ import annotations

import pytest


# ── SlackSessionStore ─────────────────────────────────────────────────────

class TestSlackSessionStore:
    def test_create_and_get(self, tmp_path):
        from theorycraft.slack.session_store import SlackSessionStore
        store = SlackSessionStore(tmp_path / "test.db")
        session = store.create("ts1", "C123", "my-session", "/tmp/my.db", "uuid1")

        assert session.thread_ts == "ts1"
        assert session.channel == "C123"
        assert session.session_name == "my-session"
        assert session.session_db_path == "/tmp/my.db"
        assert session.thread_id == "uuid1"
        assert session.status == "waiting"

        fetched = store.get("ts1")
        assert fetched is not None
        assert fetched.session_name == "my-session"
        assert fetched.status == "waiting"

    def test_get_missing_returns_none(self, tmp_path):
        from theorycraft.slack.session_store import SlackSessionStore
        store = SlackSessionStore(tmp_path / "test.db")
        assert store.get("nonexistent") is None

    def test_set_status_transitions(self, tmp_path):
        from theorycraft.slack.session_store import SlackSessionStore
        store = SlackSessionStore(tmp_path / "test.db")
        store.create("ts1", "C", "s", "/tmp/s.db", "u")

        store.set_status("ts1", "running")
        assert store.get("ts1").status == "running"

        store.set_status("ts1", "complete")
        assert store.get("ts1").status == "complete"

    def test_list_active_excludes_complete(self, tmp_path):
        from theorycraft.slack.session_store import SlackSessionStore
        store = SlackSessionStore(tmp_path / "test.db")
        store.create("ts1", "C", "s1", "/tmp/s1.db", "u1")
        store.create("ts2", "C", "s2", "/tmp/s2.db", "u2")
        store.create("ts3", "C", "s3", "/tmp/s3.db", "u3")
        store.set_status("ts2", "complete")

        active = store.list_active()
        thread_ids = {s.thread_ts for s in active}
        assert "ts1" in thread_ids
        assert "ts3" in thread_ids
        assert "ts2" not in thread_ids

    def test_list_active_includes_running_and_waiting(self, tmp_path):
        from theorycraft.slack.session_store import SlackSessionStore
        store = SlackSessionStore(tmp_path / "test.db")
        store.create("ts1", "C", "s1", "/tmp/s1.db", "u1")
        store.create("ts2", "C", "s2", "/tmp/s2.db", "u2")
        store.set_status("ts1", "running")

        active = store.list_active()
        assert len(active) == 2

    def test_duplicate_thread_ts_raises(self, tmp_path):
        from theorycraft.slack.session_store import SlackSessionStore
        import sqlite3
        store = SlackSessionStore(tmp_path / "test.db")
        store.create("ts1", "C", "s", "/tmp/s.db", "u")
        with pytest.raises(sqlite3.IntegrityError):
            store.create("ts1", "C", "s2", "/tmp/s2.db", "u2")

    def test_multiple_stores_share_same_db(self, tmp_path):
        from theorycraft.slack.session_store import SlackSessionStore
        db = tmp_path / "shared.db"
        store1 = SlackSessionStore(db)
        store2 = SlackSessionStore(db)
        store1.create("ts1", "C", "s", "/tmp/s.db", "u")
        assert store2.get("ts1") is not None


# ── Formatter ─────────────────────────────────────────────────────────────

class TestSlackFormatter:
    def test_intake_format_has_header_and_body(self):
        from theorycraft.slack.formatter import format_interrupt
        text, blocks = format_interrupt({"type": "intake"})
        assert len(blocks) >= 2
        assert "New Theorycraft" in blocks[0]["text"]["text"] or "theorycraft" in text.lower()

    def test_clarify_format_includes_round_and_questions(self):
        from theorycraft.slack.formatter import format_interrupt
        questions = "1. Who are the users?\n2. What platform?"
        text, blocks = format_interrupt({"type": "clarify", "questions": questions, "round": 1})
        header = blocks[0]["text"]["text"]
        assert "Round 1" in header
        body = blocks[1]["text"]["text"]
        assert "Who are the users?" in body
        assert "What platform?" in body

    def test_clarify_shows_correct_round_number(self):
        from theorycraft.slack.formatter import format_interrupt
        _, blocks = format_interrupt({"type": "clarify", "questions": "Q?", "round": 3})
        assert "Round 3" in blocks[0]["text"]["text"]

    def test_ideate_format_includes_round_and_concept(self):
        from theorycraft.slack.formatter import format_interrupt
        _, blocks = format_interrupt({"type": "ideate", "concept": "A great product idea!", "round": 2})
        assert "Round 2" in blocks[0]["text"]["text"]
        assert "A great product idea!" in blocks[1]["text"]["text"]

    def test_validate_format_includes_all_commands(self):
        from theorycraft.slack.formatter import format_interrupt
        _, blocks = format_interrupt({"type": "validate", "summary": "services (2)", "revision_round": 0})
        command_text = " ".join(
            b["text"]["text"] for b in blocks
            if b.get("type") == "section" and "text" in b
        )
        assert "approve" in command_text
        assert "revise" in command_text
        assert "restart" in command_text

    def test_validate_shows_revision_round_when_nonzero(self):
        from theorycraft.slack.formatter import format_interrupt
        _, blocks = format_interrupt({"type": "validate", "summary": "services (1)", "revision_round": 2})
        header = blocks[0]["text"]["text"]
        assert "revision 2" in header

    def test_validate_no_revision_label_when_round_zero(self):
        from theorycraft.slack.formatter import format_interrupt
        _, blocks = format_interrupt({"type": "validate", "summary": "services (1)", "revision_round": 0})
        header = blocks[0]["text"]["text"]
        assert "revision" not in header

    def test_completion_shows_output_path(self):
        from theorycraft.slack.formatter import format_completion
        text, blocks = format_completion({
            "output_path": "/home/user/.theorycraft/output/my-app/product.json",
            "github_output_url": "",
            "errors": [],
            "notifications_sent": [],
        })
        assert "Complete" in blocks[0]["text"]["text"]
        assert "my-app/product.json" in blocks[1]["text"]["text"]

    def test_completion_shows_github_url(self):
        from theorycraft.slack.formatter import format_completion
        _, blocks = format_completion({
            "output_path": "/tmp/product.json",
            "github_output_url": "https://github.com/org/myapp-spec",
            "errors": [],
            "notifications_sent": [],
        })
        assert "github.com" in blocks[1]["text"]["text"]

    def test_completion_shows_errors(self):
        from theorycraft.slack.formatter import format_completion
        _, blocks = format_completion({
            "output_path": "",
            "github_output_url": "",
            "errors": ["github rate limited"],
            "notifications_sent": [],
        })
        assert "rate limited" in blocks[1]["text"]["text"]

    def test_unknown_type_shows_content(self):
        from theorycraft.slack.formatter import format_interrupt
        text, blocks = format_interrupt({"type": "mystery", "content": "please respond"})
        body = blocks[0]["text"]["text"]
        assert "please respond" in body

    def test_long_concept_truncated(self):
        from theorycraft.slack.formatter import format_interrupt
        long_text = "x" * 5000
        _, blocks = format_interrupt({"type": "ideate", "concept": long_text, "round": 1})
        body = blocks[1]["text"]["text"]
        assert len(body) < 5000
        assert "truncated" in body

    def test_format_error(self):
        from theorycraft.slack.formatter import format_error
        text, blocks = format_error("Graph crashed")
        assert "Graph crashed" in text
        assert ":x:" in blocks[0]["text"]["text"]
        assert "Graph crashed" in blocks[0]["text"]["text"]

    def test_format_thinking_returns_blocks(self):
        from theorycraft.slack.formatter import format_thinking
        blocks = format_thinking()
        assert len(blocks) >= 1
        assert "thinking" in str(blocks).lower()


# ── unique_session_name ───────────────────────────────────────────────────

class TestUniqueSessionName:
    def test_returns_base_when_no_conflict(self, tmp_path):
        from theorycraft.utils import unique_session_name
        assert unique_session_name("my-app", tmp_path) == "my-app"

    def test_appends_2_on_first_conflict(self, tmp_path):
        from theorycraft.utils import unique_session_name
        (tmp_path / "my-app.db").touch()
        assert unique_session_name("my-app", tmp_path) == "my-app-2"

    def test_appends_3_on_two_conflicts(self, tmp_path):
        from theorycraft.utils import unique_session_name
        (tmp_path / "my-app.db").touch()
        (tmp_path / "my-app-2.db").touch()
        assert unique_session_name("my-app", tmp_path) == "my-app-3"

    def test_unrelated_files_do_not_conflict(self, tmp_path):
        from theorycraft.utils import unique_session_name
        (tmp_path / "other-app.db").touch()
        assert unique_session_name("my-app", tmp_path) == "my-app"
