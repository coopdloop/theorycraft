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

    # Post a "thinking" indicator so the user knows we received their message.
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
        logger.exception("Graph invocation failed for session %s", session.session_name)
        text, blocks = format_error(f"Something went wrong: {exc}")
        await say(text=text, blocks=blocks, thread_ts=session.thread_ts)
        store.set_status(session.thread_ts, "waiting")
        return False
    finally:
        try:
            await client.chat_delete(channel=session.channel, ts=thinking_msg["ts"])
        except Exception:
            pass

    interrupts = result.get("__interrupt__")

    if not interrupts:
        # Graph ran to completion.
        store.set_status(session.thread_ts, "complete")
        text, blocks = format_completion(result)
        await say(text=text, blocks=blocks, thread_ts=session.thread_ts)

        # Optionally archive the spec to the theorycraft repo.
        await _maybe_archive(result, session)
        return True

    raw = interrupts[0]
    interrupt_value = raw.value if hasattr(raw, "value") else raw
    if not isinstance(interrupt_value, dict):
        interrupt_value = {"type": "unknown", "content": str(interrupt_value)}

    node_type = interrupt_value.get("type", "")
    if node_type not in {"intake", "clarify", "ideate", "validate"}:
        # Design node in progress — post a status update without changing flow.
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
