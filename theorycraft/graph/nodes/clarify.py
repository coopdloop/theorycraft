from __future__ import annotations

from langgraph.types import interrupt

from theorycraft.graph.state import ClarificationPair, TheoryCraftState
from theorycraft.llm.router import simple_call
from theorycraft.telemetry.langfuse import node_trace

_QUESTION_SYSTEM = """\
You are a product strategist helping to clarify a product idea before building a spec.
Given the idea and any existing context, generate 3-4 targeted clarifying questions.
Focus on: target users, key constraints, scale expectations, must-have vs nice-to-have.
Return ONLY the questions as a numbered list. No preamble."""


@node_trace("clarify")
def clarify(state: TheoryCraftState) -> dict:
    """Ask the user clarifying questions to fill in gaps before ideation."""
    idea = state["raw_idea"]
    existing = state.get("clarifications", [])
    context_summary = "\n".join(f"Q: {c['question']}\nA: {c['answer']}" for c in existing)

    messages = [
        {"role": "system", "content": _QUESTION_SYSTEM},
        {
            "role": "user",
            "content": f"Product idea: {idea}\n\nContext so far:\n{context_summary or 'None yet'}",
        },
    ]
    questions_text = simple_call(messages, temperature=0.3)

    result = interrupt(
        {
            "type": "clarify",
            "questions": questions_text,
            "round": state.get("clarify_round", 0) + 1,
        }
    )

    # result is expected to be a list of {question, answer} dicts or a single answer string
    new_pairs: list[ClarificationPair]
    if isinstance(result, list):
        new_pairs = [ClarificationPair(question=q, answer=a) for q, a in result]
    elif isinstance(result, dict) and "pairs" in result:
        new_pairs = result["pairs"]
    else:
        # Treat as free-form answer to all questions
        new_pairs = [ClarificationPair(question=questions_text, answer=str(result))]

    return {
        "clarifications": new_pairs,
        "clarify_round": state.get("clarify_round", 0) + 1,
        "needs_more_clarification": False,
    }
