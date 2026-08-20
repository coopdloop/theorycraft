from __future__ import annotations

from langgraph.types import interrupt

from theorycraft.graph.state import TheoryCraftState
from theorycraft.llm.router import simple_call
from theorycraft.telemetry.langfuse import node_trace

_IDEATE_SYSTEM = """\
You are a senior product architect and creative technologist.
Your job is to collaboratively theory-craft a product idea with the user.
Based on the idea and any clarifications provided, generate a rich product concept overview covering:
- Product name and memorable tagline
- Core problem solved and why it matters
- Key features and user flows
- Suggested tech stack (be specific: Go/Python services, React SPA, PostgreSQL, etc.)
- What makes this product distinctive

Be enthusiastic, opinionated, and specific. This is a collaborative brainstorm — invite the user to steer.
End with: "What would you like to adjust or add? (Type /ready when you're happy with the direction)"
"""

_REFINE_SYSTEM = """\
You are a senior product architect continuing a product theory-crafting session.
Incorporate the user's feedback and expand the concept accordingly.
Be specific about technical choices. End with the same invitation to continue or type /ready.
"""


@node_trace("ideate")
def ideate(state: TheoryCraftState) -> dict:
    """Collaborative theory-crafting loop. Continues until user signals /ready."""
    idea = state["raw_idea"]
    clarifications = state.get("clarifications", [])
    rounds = state.get("ideation_rounds", 0) if "ideation_rounds" in state else 0
    prev_concept = state.get("concept_summary", "")

    context_lines = [f"Original idea: {idea}"]
    if clarifications:
        context_lines.append("\nClarifications:")
        for c in clarifications:
            context_lines.append(f"  Q: {c['question']}\n  A: {c['answer']}")

    if rounds == 0 or not prev_concept:
        system = _IDEATE_SYSTEM
        user_content = "\n".join(context_lines)
    else:
        system = _REFINE_SYSTEM
        user_content = f"Previous concept:\n{prev_concept}\n\n{''.join(context_lines)}"

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    concept = simple_call(messages, temperature=0.7)

    result = interrupt(
        {
            "type": "ideate",
            "concept": concept,
            "round": rounds + 1,
            "hint": "Type /ready to proceed to spec generation, or continue refining.",
        }
    )

    user_input: str = result if isinstance(result, str) else result.get("input", "")

    if user_input.strip().lower() in {"/ready", "ready", "/go", "go"}:
        return {
            "concept_summary": concept,
            "concept_approved": True,
        }

    if user_input.strip().lower() in {"/clarify", "clarify", "/more", "more"}:
        return {
            "concept_summary": concept,
            "concept_approved": False,
            "needs_more_clarification": True,
        }

    # User gave more feedback — append to concept and loop
    refined = f"{concept}\n\nUser feedback: {user_input}"
    return {
        "concept_summary": refined,
        "concept_approved": False,
        "needs_more_clarification": False,
    }
