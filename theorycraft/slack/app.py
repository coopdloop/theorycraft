from __future__ import annotations

import asyncio
import logging
import re
import signal
import uuid

from langgraph.types import Command

logger = logging.getLogger(__name__)

# Resolved at startup after auth_test()
_bot_user_id: str = ""
_store = None

# Limits how many graph invocations run concurrently across all sessions.
_MAX_CONCURRENT_GRAPHS = 4
_graph_sem: asyncio.Semaphore | None = None


def _sem() -> asyncio.Semaphore:
    global _graph_sem
    if _graph_sem is None:
        _graph_sem = asyncio.Semaphore(_MAX_CONCURRENT_GRAPHS)
    return _graph_sem


def _get_store():
    global _store
    if _store is None:
        from theorycraft.config import get_settings
        from theorycraft.slack.session_store import SlackSessionStore
        cfg = get_settings()
        _store = SlackSessionStore(cfg.sessions_dir / "slack_sessions.db")
    return _store


def _strip_mention(text: str, bot_user_id: str) -> str:
    """Remove the @bot mention from message text."""
    return re.sub(rf"<@{re.escape(bot_user_id)}>", "", text).strip()


def _build_app(bot_token: str):
    from slack_bolt.async_app import AsyncApp
    from theorycraft.config import get_settings
    from theorycraft.slack.adapter import build_initial_state, drive_graph

    app = AsyncApp(token=bot_token)

    # ── @mention → start or drive a session ──────────────────────────────

    @app.event("app_mention")
    async def handle_mention(event, say, client):
        global _bot_user_id

        thread_ts = event.get("thread_ts") or event["ts"]
        channel = event["channel"]
        raw_text = event.get("text", "")
        text = _strip_mention(raw_text, _bot_user_id).strip()

        logger.info("slack.mention  channel=%s  thread=%s  text=%r", channel, thread_ts, text[:120])

        store = _get_store()
        session = store.get(thread_ts)

        # ── Resume an existing active session ─────────────────────────────
        if session and session.status == "running":
            logger.debug("slack.mention  thread=%s  dropped (already running)", thread_ts)
            return

        if session and session.status == "waiting":
            logger.info("slack.mention  resuming session=%s", session.session_name)
            if not text:
                await say(
                    text="_Session active — reply in this thread to continue._",
                    thread_ts=thread_ts,
                )
                return
            store.set_status(thread_ts, "running")
            async with _sem():
                complete = await drive_graph(say, client, store, session, Command(resume=text))
            if not complete:
                store.set_status(thread_ts, "waiting")
            return

        if session and session.status == "complete":
            logger.info("slack.mention  thread=%s  session already complete", thread_ts)
            await say(
                text="_This session is complete. Mention me in a new message to start a fresh one._",
                thread_ts=thread_ts,
            )
            return

        # ── Start a new session ───────────────────────────────────────────
        cfg = get_settings()
        from theorycraft import naming
        from theorycraft.utils import unique_session_name

        session_id = str(uuid.uuid4())
        base_name = naming.idea_slug(text) if text else f"session-{session_id[:8]}"
        if not base_name:
            base_name = f"session-{session_id[:8]}"
        session_name = unique_session_name(base_name, cfg.sessions_dir)
        output_dir = str(cfg.output_dir / session_name)
        session_db_path = str(cfg.sessions_dir / f"{session_name}.db")

        logger.info("slack.session  create  name=%s  id=%s  channel=%s", session_name, session_id, channel)

        session = store.create(thread_ts, channel, session_name, session_db_path, session_id)
        state = build_initial_state(text, session_name, session_id, output_dir)

        store.set_status(thread_ts, "running")
        async with _sem():
            complete = await drive_graph(say, client, store, session, state)
        if not complete:
            store.set_status(thread_ts, "waiting")

    # ── Thread replies → drive the active session ─────────────────────────

    @app.event("message")
    async def handle_message(event, say, client):
        # Ignore bot messages and non-thread messages.
        if event.get("bot_id") or event.get("subtype"):
            return
        thread_ts = event.get("thread_ts")
        if not thread_ts:
            return

        store = _get_store()
        session = store.get(thread_ts)

        if not session:
            return
        if session.status == "complete":
            return
        if session.status == "running":
            logger.debug("slack.message  thread=%s  dropped (already running)", thread_ts)
            return

        user_input = event.get("text", "").strip()
        if not user_input:
            return

        logger.info("slack.message  session=%-30s  text=%r", session.session_name, user_input[:120])

        store.set_status(thread_ts, "running")
        async with _sem():
            complete = await drive_graph(say, client, store, session, Command(resume=user_input))
        if not complete:
            store.set_status(thread_ts, "waiting")

    return app


async def _run(bot_token: str, app_token: str) -> None:
    global _bot_user_id
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    app = _build_app(bot_token)

    auth = await app.client.auth_test()
    _bot_user_id = auth["user_id"]
    logger.info("Theorycraft Slack bot started as @%s (%s)", auth["user"], _bot_user_id)

    handler = AsyncSocketModeHandler(app, app_token)

    # Graceful shutdown on SIGTERM / SIGINT
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    start_task = asyncio.create_task(handler.start_async())
    logger.info("Bot running — press Ctrl+C to stop gracefully.")

    await stop_event.wait()

    logger.info("Shutdown signal received — closing bot…")
    await handler.close_async()
    start_task.cancel()
    try:
        await start_task
    except (asyncio.CancelledError, Exception):
        pass
    logger.info("Bot stopped.")


def _setup_logging() -> None:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.theme import Theme

    theme = Theme({
        "logging.level.info":    "bold cyan",
        "logging.level.warning": "bold yellow",
        "logging.level.error":   "bold red",
        "logging.level.debug":   "dim white",
        "log.time":              "dim white",
        "log.level":             "bold",
    })
    console = Console(theme=theme, highlight=True)

    # Shorten theorycraft.* prefixes so they fit neatly in the name column.
    _name_map = [
        ("theorycraft.slack.",       "slack."),
        ("theorycraft.llm.",         "llm."),
        ("theorycraft.graph.nodes.", "node."),
        ("theorycraft.integrations.","integr."),
        ("theorycraft.",             "tc."),
    ]

    class _ShortenName(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            for old, new in _name_map:
                if record.name.startswith(old):
                    record.name = new + record.name[len(old):]
                    break
            return True

    handler = RichHandler(
        console=console,
        show_time=True,
        show_level=True,
        show_path=False,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        markup=False,          # don't interpret [ in log messages as markup
        log_time_format="[%H:%M:%S]",
        omit_repeated_times=False,
    )
    handler.addFilter(_ShortenName())

    # force=True overrides any handlers already set by litellm / langfuse imports.
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[handler], force=True)

    # Silence noisy third-party loggers.
    for _noisy in ("slack_bolt", "slack_sdk", "httpx", "httpcore", "litellm", "LiteLLM"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    # LiteLLM also has its own verbose flag outside the logging module.
    try:
        import litellm as _ll
        _ll.verbose = False
        _ll.suppress_debug_info = True
    except Exception:
        pass


def start() -> None:
    """Entry point: `uv run tc-slack` or `python -m theorycraft.slack.app`."""
    _setup_logging()

    from theorycraft.config import get_settings
    cfg = get_settings()

    if not cfg.slack_bot_enabled:
        raise SystemExit(
            "SLACK_BOT_TOKEN and SLACK_APP_TOKEN must both be set to run the Slack bot."
        )

    asyncio.run(_run(cfg.slack_bot_token, cfg.slack_app_token))


if __name__ == "__main__":
    start()
