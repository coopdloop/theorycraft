from __future__ import annotations

# Slack text block limit with a safe margin
_LIMIT = 2800


def _trunc(text: str, limit: int = _LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n_…[truncated]_"


def format_interrupt(interrupt_value: dict) -> tuple[str, list[dict]]:
    """Convert a graph interrupt payload to (fallback_text, Slack blocks)."""
    kind = interrupt_value.get("type", "unknown")

    if kind == "intake":
        text = "What idea would you like to theorycraft today?"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": ":bulb: New Theorycraft Session"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*What product idea would you like to theorycraft?*\nDescribe it — as specific or vague as you like.",
                },
            },
        ]

    elif kind == "clarify":
        questions = interrupt_value.get("questions", "")
        round_num = interrupt_value.get("round", 1)
        text = f"Clarifying questions — round {round_num}"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f":question: Clarifying Questions — Round {round_num}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": _trunc(questions)}},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "_Reply with your answers in this thread._"}]},
        ]

    elif kind == "ideate":
        concept = interrupt_value.get("concept", "")
        round_num = interrupt_value.get("round", 1)
        text = f"Theorycraft round {round_num}"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f":brain: Theorycraft — Round {round_num}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": _trunc(concept)}},
            {"type": "divider"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "_Reply with feedback to refine the idea, or type `/ready` to proceed to spec generation._",
                    }
                ],
            },
        ]

    elif kind == "validate":
        summary = interrupt_value.get("summary", "")
        revision_round = interrupt_value.get("revision_round", 0)
        round_label = f" (revision {revision_round})" if revision_round else ""
        text = "Review your spec"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f":mag: Review Spec{round_label}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"```\n{_trunc(summary, 1600)}\n```"}},
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Commands:*\n"
                        "• `approve` — write product.json and publish\n"
                        "• `revise <section>: <feedback>` — refine a section\n"
                        "• `restart` — go back to ideation"
                    ),
                },
            },
        ]

    else:
        content = str(interrupt_value.get("content", interrupt_value))
        text = "Agent needs input"
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": _trunc(content)}}]

    return text, blocks


def format_completion(state: dict) -> tuple[str, list[dict]]:
    """Format the final graph state as a Slack completion message."""
    output_path = state.get("output_path", "")
    github_url = state.get("github_output_url", "")
    errors = state.get("errors", [])
    notifications = state.get("notifications_sent", [])

    lines = []
    if output_path:
        lines.append(f"*Spec:* `{output_path}`")
    if github_url:
        lines.append(f"*GitHub:* <{github_url}|View repo / PR>")
    for n in notifications:
        status = ":white_check_mark:" if n.get("success") else ":x:"
        lines.append(f"{status} {n.get('channel', 'notification')}")
    for e in errors:
        lines.append(f":warning: {e}")

    body = "\n".join(lines) if lines else "Done."
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": ":white_check_mark: Theorycraft Complete"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
    ]
    return "Theorycraft complete!", blocks


def format_error(message: str) -> tuple[str, list[dict]]:
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": f":x: {message}"}}]
    return message, blocks


def format_thinking() -> list[dict]:
    return [{"type": "context", "elements": [{"type": "mrkdwn", "text": ":hourglass_flowing_sand: _thinking..._"}]}]
