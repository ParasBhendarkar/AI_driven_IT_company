from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.graph import GraphState

from core.retry import (
    should_auto_retry,
    should_escalate_critic,
    should_escalate_human,
    is_immediate_human,
)


def route_after_qa(state: GraphState) -> str:
    task = state["task"]
    qa = task.qa_result

    if qa is None:
        return "escalate_human"

    if qa.status == "pass" and getattr(qa, "acceptance_met", True):
        return "ciso"

    if should_auto_retry(task.retry_count, qa):
        return "developer"

    if should_escalate_critic(task.retry_count):
        return "critic"

    return "escalate_human"


def route_after_ciso(state: GraphState) -> str:
    task = state["task"]
    gate = task.ciso_gate

    if gate is None:
        return "escalate_human"

    decision = getattr(gate, "decision", None) or (
        "block" if getattr(gate, "blocked", False) else "approve"
    )

    if decision == "approve":
        return "deploy"

    if is_immediate_human(gate):
        return "escalate_human"

    return "developer"


def route_after_critic(state: GraphState) -> str:
    task = state["task"]

    if should_escalate_human(task.retry_count):
        return "escalate_human"

    return "developer"
