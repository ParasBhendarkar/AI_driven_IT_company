from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from langgraph.graph import StateGraph, END

from memory.short_term import save_state, publish_event
from memory.long_term import retrieve_memory
from models.schemas import TaskStatus, TaskState
from models.events import AgentEvent, TaskStatusEvent
from core.router import route_after_qa, route_after_ciso, route_after_critic


class GraphState(TypedDict):
    task: TaskState
    events: list[AgentEvent]


def _compute_progress(status: TaskStatus | str) -> int:
    mapping = {
        "pending": 5,
        "running": 20,
        "retrying": 35,
        "qa_review": 50,
        "security_review": 70,
        "critic_review": 45,
        "awaiting_deploy": 85,
        "deployed": 100,
        "failed": 0,
        "escalated": 30,
        "blocked": 40,
    }
    s = status.value if hasattr(status, "value") else str(status)
    return mapping.get(s, 0)


async def _emit(state: GraphState, description: str, event_type: str = "info", payload: dict | None = None) -> None:
    """Publish an AgentEvent to Redis pub/sub (feeds SSE stream)."""
    task = state["task"]
    event = AgentEvent(
        task_id=task.task_id,
        agent=str(task.current_agent.value if hasattr(task.current_agent, "value") else task.current_agent),
        description=description,
        type=event_type,
        payload=payload,
    )
    state["events"].append(event)
    await publish_event(task.task_id, event)


async def _set_status(state: GraphState, status: TaskStatus, agent: str) -> None:
    """Update task status + current_agent, save to Redis, publish status event."""
    task = state["task"]
    task.status = status
    task.current_agent = agent
    task.updated_at = datetime.utcnow()
    task.progress = _compute_progress(status)
    await save_state(task)
    await publish_event(
        task.task_id,
        TaskStatusEvent(
            task_id=task.task_id,
            status=status.value if hasattr(status, "value") else str(status),
            current_agent=agent,
            retry_count=task.retry_count,
            progress=task.progress,
        ),
    )


async def node_load_memory(state: GraphState) -> GraphState:
    """Retrieve semantic memory hits relevant to this task."""
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "Orchestrator")
    await _emit(state, "Loading memory context...")

    query = f"{task.title} {task.description}"
    hits = await retrieve_memory(query, top_k=3)
    task.memory_hits = [h.model_dump() for h in hits]

    hit_count = len(hits)
    await _emit(state, f"Memory loaded — {hit_count} relevant hits found")
    await save_state(task)
    return state


async def node_run_developer(state: GraphState) -> GraphState:
    from agent.developer import DeveloperAgent

    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "Developer")
    updated_task = await DeveloperAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_qa(state: GraphState) -> GraphState:
    from agent.qa import QAAgent

    task = state["task"]
    await _set_status(state, TaskStatus.QA_REVIEW, "QA")
    updated_task = await QAAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_ciso(state: GraphState) -> GraphState:
    from agent.ciso import CISOAgent

    task = state["task"]
    await _set_status(state, TaskStatus.SECURITY_REVIEW, "CISO")
    updated_task = await CISOAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_critic(state: GraphState) -> GraphState:
    from agent.critic import CriticAgent

    task = state["task"]
    await _set_status(state, TaskStatus.CRITIC_REVIEW, "Critic")
    updated_task = await CriticAgent().run(task)
    state["task"] = updated_task
    return state


async def node_escalate_human(state: GraphState) -> GraphState:
    """Block the task and write an EscalationRow to Postgres."""
    from database import async_session_maker
    from models.db import EscalationRow
    import uuid

    task = state["task"]
    await _set_status(state, TaskStatus.ESCALATED, "Orchestrator")

    reason = task.last_error or f"Task failed after {task.retry_count} attempts"
    recommendation = None
    if task.critic_output:
        recommendation = getattr(task.critic_output, "fix", None) or getattr(task.critic_output, "recommendation", None)

    async with async_session_maker() as session:
        row = EscalationRow(
            id=str(uuid.uuid4()),
            task_id=task.task_id,
            escalation_type="max_retries",
            reason=reason,
            recommendation=recommendation,
            resolved=False,
        )
        session.add(row)
        await session.commit()

    await _emit(
        state,
        f"Escalated to human — {reason}",
        event_type="warning",
        payload={"recommendation": recommendation},
    )
    return state


async def node_deploy(state: GraphState) -> GraphState:
    from agent.devops import DevOpsAgent

    task = state["task"]
    await _set_status(state, TaskStatus.AWAITING_DEPLOY, "DevOps")
    updated_task = await DevOpsAgent().run(task)
    state["task"] = updated_task
    return state


async def node_write_memory(state: GraphState) -> GraphState:
    """Extract lessons from completed task and store in Qdrant + Postgres."""
    from database import async_session_maker
    from models.db import MemoryEntryRow
    from memory.long_term import store_memory
    from models.schemas import MemoryEntry
    import uuid
    from datetime import datetime

    task = state["task"]
    await _emit(state, "Writing lessons to long-term memory...")

    lessons: list[str] = []

    if task.qa_result and task.error_history:
        lessons.append(
            f"Task '{task.title}' needed {task.retry_count} retries. Root errors: {'; '.join(task.error_history[-3:])}"
        )

    if task.ciso_gate and getattr(task.ciso_gate, "findings", None):
        for finding in task.ciso_gate.findings:
            desc = getattr(finding, "description", str(finding))
            lessons.append(f"Security: {desc}")

    if task.critic_output:
        root_cause = getattr(task.critic_output, "root_cause", getattr(task.critic_output, "summary", ""))
        fix = getattr(task.critic_output, "fix", getattr(task.critic_output, "recommendation", ""))
        if root_cause:
            lessons.append(f"Root cause pattern: {root_cause}. Fix: {fix}")

    tags = ["task-complete", task.repo.split("/")[-1]]
    if task.qa_result:
        tags.append("qa-passed")

    for lesson in lessons:
        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            content=lesson,
            tags=tags,
            source_task_id=task.task_id,
            agent="Orchestrator",
            date=datetime.utcnow().isoformat(),
        )
        await store_memory(entry)

        async with async_session_maker() as session:
            row = MemoryEntryRow(
                id=entry.id,
                content=lesson,
                tags=tags,
                source_task_id=task.task_id,
            )
            session.add(row)
            await session.commit()

    await _emit(
        state,
        f"{len(lessons)} lessons stored to memory",
        event_type="success",
    )
    return state


_builder = StateGraph(GraphState)

_builder.add_node("load_memory", node_load_memory)
_builder.add_node("developer", node_run_developer)
_builder.add_node("qa", node_run_qa)
_builder.add_node("ciso", node_run_ciso)
_builder.add_node("critic", node_run_critic)
_builder.add_node("escalate_human", node_escalate_human)
_builder.add_node("deploy", node_deploy)
_builder.add_node("write_memory", node_write_memory)

_builder.set_entry_point("load_memory")
_builder.add_edge("load_memory", "developer")
_builder.add_edge("developer", "qa")

_builder.add_conditional_edges(
    "qa",
    route_after_qa,
    {
        "ciso": "ciso",
        "developer": "developer",
        "critic": "critic",
        "escalate_human": "escalate_human",
    },
)
_builder.add_conditional_edges(
    "ciso",
    route_after_ciso,
    {
        "deploy": "deploy",
        "developer": "developer",
        "escalate_human": "escalate_human",
    },
)
_builder.add_conditional_edges(
    "critic",
    route_after_critic,
    {
        "developer": "developer",
        "escalate_human": "escalate_human",
    },
)

_builder.add_edge("escalate_human", END)
_builder.add_edge("deploy", "write_memory")
_builder.add_edge("write_memory", END)

graph = _builder.compile()
