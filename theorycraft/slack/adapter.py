from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from langgraph.types import Command

from theorycraft.graph.builder import GraphSession
from theorycraft.graph.state import TheoryCraftState, initial_state
from theorycraft.slack.formatter import (
    format_completion,
    format_error,
    format_interrupt,
    format_thinking,
)
from theorycraft.slack.session_store import SlackSession, SlackSessionStore

logger = logging.getLogger(__name__)

# Each graph invocation is CPU+IO bound and synchronous — run in a thread pool.
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tc-graph")


def _invoke(session_db_path: str, thread_id: str, input_data) -> dict:
    """Synchronous graph.invoke — runs inside the thread pool."""
    with GraphSession(session_db_path) as gs:
        return gs.graph.invoke(
            input_data,
            {"configurable": {"thread_id": thread_id}},
        )


def _log_state(state: dict, session_name: str) -> None:
    """Log a concise snapshot of meaningful state fields."""
    parts: list[str] = []

    if state.get("raw_idea"):
        idea = state["raw_idea"][:60].replace("\n", " ")
        parts.append(f"idea={idea!r}")

    clarifications = state.get("clarifications", [])
    if clarifications:
        parts.append(f"clarifications={len(clarifications)}")

    if state.get("concept_summary"):
        parts.append(f"concept={'approved' if state.get('concept_approved') else 'draft'}")

    for key, label in [
        ("services_draft", "services"),
        ("api_routes_draft", "api_routes"),
        ("db_schema_draft", "db_schema"),
        ("frontend_draft", "frontend"),
        ("sdk_draft", "sdk"),
        ("architecture_draft", "architecture"),
    ]:
        if state.get(key):
            parts.append(f"{label}=✓")

    if state.get("spec_approved"):
        parts.append("spec=approved")
    elif state.get("sections_to_revise"):
        parts.append(f"revisions={len(state['sections_to_revise'])}")

    if state.get("output_path"):
        parts.append(f"output={state['output_path']}")

    if state.get("github_output_url"):
        parts.append(f"github={state['github_output_url']}")

    errors = state.get("errors", [])
    if errors:
        parts.append(f"errors={len(errors)}")

    logger.info("[%s] state  %s", session_name, "  ".join(parts) if parts else "(empty)")


async def drive_graph(
    say,
    client,
    store: SlackSessionStore,
    session: SlackSession,
    input_data,
) -> bool:
    """
    Drive one graph step: invoke the graph, then post the interrupt or
    completion back to the Slack thread.

    Returns True if the session is complete, False if it's waiting for
    the next user reply.
    """
    loop = asyncio.get_running_loop()

    # Log user input (Command resumes carry the user's text).
    if hasattr(input_data, "resume"):
        user_text = str(input_data.resume)[:200].replace("\n", " ")
        logger.info("[%s] user → %r", session.session_name, user_text)
    else:
        logger.info("[%s] session start  thread=%s", session.session_name, session.thread_ts)

    logger.info("[%s] graph.invoke → starting", session.session_name)

    thinking_msg = await say(
        text="thinking...",
        blocks=format_thinking(),
        thread_ts=session.thread_ts,
    )

    try:
        result = await loop.run_in_executor(
            _executor,
            _invoke,
            session.session_db_path,
            session.thread_id,
            input_data,
        )
    except Exception as exc:
        logger.exception("[%s] graph.invoke failed", session.session_name)
        text, blocks = format_error(f"Something went wrong: {exc}")
        await say(text=text, blocks=blocks, thread_ts=session.thread_ts)
        store.set_status(session.thread_ts, "waiting")
        return False
    finally:
        try:
            await client.chat_delete(channel=session.channel, ts=thinking_msg["ts"])
        except Exception:
            pass

    _log_state(result, session.session_name)

    interrupts = result.get("__interrupt__")

    if not interrupts:
        logger.info("[%s] session complete → output=%s", session.session_name, result.get("output_path", "none"))
        store.set_status(session.thread_ts, "complete")
        text, blocks = format_completion(result)
        await say(text=text, blocks=blocks, thread_ts=session.thread_ts)
        await _maybe_archive(result, session)
        return True

    raw = interrupts[0]
    interrupt_value = raw.value if hasattr(raw, "value") else raw
    if not isinstance(interrupt_value, dict):
        interrupt_value = {"type": "unknown", "content": str(interrupt_value)}

    node_type = interrupt_value.get("type", "")
    logger.info(
        "[%s] interrupt  type=%-10s  round=%s",
        session.session_name,
        node_type,
        interrupt_value.get("round", interrupt_value.get("revision_round", "-")),
    )

    if node_type not in {"intake", "clarify", "ideate", "validate"}:
        await say(
            text=f"Designing {node_type}…",
            blocks=[{"type": "context", "elements": [{"type": "mrkdwn", "text": f":gear: _Designing {node_type}…_"}]}],
            thread_ts=session.thread_ts,
        )

    text, blocks = format_interrupt(interrupt_value)
    await say(text=text, blocks=blocks, thread_ts=session.thread_ts)
    store.set_status(session.thread_ts, "waiting")
    return False


async def _maybe_archive(result: dict, session: SlackSession) -> None:
    """Commit the finished spec to the archive repo if configured."""
    from theorycraft.config import get_settings
    cfg = get_settings()
    if not cfg.theorycraft_archive_repo or not cfg.github_enabled:
        return
    output_path = result.get("output_path")
    if not output_path:
        return
    try:
        from pathlib import Path
        from theorycraft.integrations.github import GitHubClient
        client = GitHubClient(cfg)
        content = Path(output_path).read_text()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            _executor,
            lambda: client.commit_files(
                cfg.theorycraft_archive_repo,
                {f"sessions/{session.session_name}/product.json": content},
                f"theorycraft: archive spec for {session.session_name}",
            ),
        )
        logger.info("Archived spec to %s", cfg.theorycraft_archive_repo)
    except Exception as exc:
        logger.warning("Archive to %s failed: %s", cfg.theorycraft_archive_repo, exc)


def build_initial_state(
    idea: str,
    session_name: str,
    session_id: str,
    output_dir: str,
    github_publish_mode: str = "repo",
    github_existing_repo: str = "",
) -> TheoryCraftState:
    from theorycraft.config import get_settings
    cfg = get_settings()
    state = initial_state(
        session_id=session_id,
        session_name=session_name,
        raw_idea=idea,
        output_dir=output_dir,
        max_clarify_rounds=cfg.max_clarify_rounds,
        max_revisions=cfg.max_revisions,
    )
    state["github_publish_mode"] = github_publish_mode
    state["github_existing_repo"] = github_existing_repo
    return state
