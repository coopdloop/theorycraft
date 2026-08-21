from __future__ import annotations

import asyncio
import logging
import threading

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
from theorycraft.utils import DESIGN_NODE_LABELS, DESIGN_NODES

logger = logging.getLogger(__name__)


def _stream_graph(
    session_db_path: str,
    thread_id: str,
    input_data,
    q: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Synchronous graph stream running in a daemon thread.

    Pushes ("node", node_name) events to the async queue as each node finishes,
    then pushes ("done", final_state_dict) or ("error", exc) when complete.
    """
    try:
        with GraphSession(session_db_path) as gs:
            config = {"configurable": {"thread_id": thread_id}}
            interrupt_seen = None

            for chunk in gs.graph.stream(input_data, config, stream_mode="updates"):
                if "__interrupt__" in chunk:
                    interrupt_seen = chunk["__interrupt__"]
                else:
                    for node_name in chunk:
                        loop.call_soon_threadsafe(q.put_nowait, ("node", node_name))

            # Build final dict: full snapshot values + interrupt if present
            snapshot = gs.graph.get_state(config)
            final = dict(snapshot.values)
            if interrupt_seen is not None:
                final["__interrupt__"] = interrupt_seen
            elif snapshot.tasks:
                for task in snapshot.tasks:
                    if getattr(task, "interrupts", None):
                        final["__interrupt__"] = tuple(task.interrupts)
                        break

            loop.call_soon_threadsafe(q.put_nowait, ("done", final))
    except Exception as exc:
        loop.call_soon_threadsafe(q.put_nowait, ("error", exc))


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


def _progress_blocks(completed: list[str]) -> list[dict]:
    lines = ["*Generating spec…*"]
    for node_name in completed:
        label = DESIGN_NODE_LABELS.get(node_name, node_name)
        lines.append(f":white_check_mark: {label}")
    return [{"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}}]


async def drive_graph(
    say,
    client,
    store: SlackSessionStore,
    session: SlackSession,
    input_data,
) -> bool:
    """Drive one graph step with live design-node progress posted to the thread.

    Returns True if the session is complete, False if awaiting the next reply.
    """
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    if hasattr(input_data, "resume"):
        user_text = str(input_data.resume)[:200].replace("\n", " ")
        logger.info("[%s]  ← user  %r", session.session_name, user_text)
    else:
        logger.info("[%s]  new session  thread=%s", session.session_name, session.thread_ts)

    logger.info("[%s]  graph → running", session.session_name)

    thinking_msg = await say(
        text="thinking...",
        blocks=format_thinking(),
        thread_ts=session.thread_ts,
    )

    # Start graph stream in daemon thread
    t = threading.Thread(
        target=_stream_graph,
        args=(session.session_db_path, session.thread_id, input_data, q, loop),
        daemon=True,
        name=f"tc-graph-{session.session_name}",
    )
    t.start()

    # Delete thinking indicator right away so progress appears cleanly
    try:
        await client.chat_delete(channel=session.channel, ts=thinking_msg["ts"])
    except Exception:
        pass

    completed_design: list[str] = []
    progress_msg_ts: str | None = None

    while True:
        event_type, data = await q.get()

        if event_type == "node":
            node_name: str = data
            if node_name in DESIGN_NODES:
                completed_design.append(node_name)
                label = DESIGN_NODE_LABELS.get(node_name, node_name)
                logger.info("[%s]  ✓ %s", session.session_name, label)

                blocks = _progress_blocks(completed_design)
                if progress_msg_ts is None:
                    msg = await say(
                        text="Generating spec…",
                        blocks=blocks,
                        thread_ts=session.thread_ts,
                    )
                    progress_msg_ts = msg["ts"]
                else:
                    try:
                        await client.chat_update(
                            channel=session.channel,
                            ts=progress_msg_ts,
                            text="Generating spec…",
                            blocks=blocks,
                        )
                    except Exception:
                        pass

        elif event_type == "error":
            logger.exception("[%s]  graph error: %s", session.session_name, data)
            if progress_msg_ts:
                try:
                    await client.chat_delete(channel=session.channel, ts=progress_msg_ts)
                except Exception:
                    pass
            text, blocks = format_error(f"Something went wrong: {data}")
            await say(text=text, blocks=blocks, thread_ts=session.thread_ts)
            store.set_status(session.thread_ts, "waiting")
            return False

        elif event_type == "done":
            result = data
            break

    # Remove the progress message before posting the final result
    if progress_msg_ts:
        try:
            await client.chat_delete(channel=session.channel, ts=progress_msg_ts)
        except Exception:
            pass

    _log_state(result, session.session_name)

    interrupts = result.get("__interrupt__")

    if not interrupts:
        logger.info("[%s]  complete  output=%s", session.session_name, result.get("output_path", "none"))
        store.set_status(session.thread_ts, "complete")
        text, blocks = format_completion(result)
        await say(text=text, blocks=blocks, thread_ts=session.thread_ts)
        await _maybe_archive(result, session)
        return True

    raw = interrupts[0] if isinstance(interrupts, (tuple, list)) else interrupts
    interrupt_value = raw.value if hasattr(raw, "value") else raw
    if not isinstance(interrupt_value, dict):
        interrupt_value = {"type": "unknown", "content": str(interrupt_value)}

    node_type = interrupt_value.get("type", "")
    round_val = interrupt_value.get("round", interrupt_value.get("revision_round", "-"))
    logger.info("[%s]  interrupt  type=%-10s  round=%s", session.session_name, node_type, round_val)

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

        loop = asyncio.get_running_loop()
        content = Path(output_path).read_text()
        gh = GitHubClient(cfg)
        await loop.run_in_executor(
            None,
            lambda: gh.commit_files(
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
