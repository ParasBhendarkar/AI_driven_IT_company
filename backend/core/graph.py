from __future__ import annotations

import logging
import operator
from datetime import datetime
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END
from langgraph.types import Send

logger = logging.getLogger(__name__)

from memory.short_term import save_state, publish_event
from memory.long_term import retrieve_memory
from models.schemas import TaskStatus, TaskState, SubTask, PullRequestSummary, RequestType
from models.events import AgentEvent, TaskStatusEvent
from core.router import (
    route_after_qa,
    route_after_ciso,
    route_after_critic,
    route_after_ceo,
    route_after_tl_review,
    route_after_tl_final,
    route_by_request_type,
    route_after_tech_lead_merge,
    route_after_qa_planner,
)


class GraphState(TypedDict):
    task: TaskState
    events: list[AgentEvent]
    # Parallel-safe: each parallel developer branch appends one entry.
    # `operator.add` is the LangGraph reducer for list fan-in.
    pull_requests: Annotated[list[PullRequestSummary], operator.add]


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
        "parallel_dev": 40,
        "merging": 75,
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
    logger.info("NODE ENTERED: load_memory")
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
 
 
async def node_route_request(state: GraphState) -> GraphState:
    """
    Entry router. Reads state['task'].request_type and emits a routing event.
    Does NOT change any agent state — routing is handled by the conditional
    edge `route_by_request_type` that follows this node.
    """
    logger.info("NODE ENTERED: route_request")
    task = state["task"]
    await _emit(
        state,
        f"Request type detected: {task.request_type.value} — routing accordingly",
        event_type="info",
        payload={"request_type": task.request_type.value},
    )
    return state
 
 
async def node_qa_planner(state: GraphState) -> GraphState:
    """
    Task path entry point. Runs before Developer on the sequential Task path.
    Reads the task description + acceptance criteria and emits a structured
    test plan into state so Developer knows what tests to make pass.
    Uses QAAgent in planning mode — no test runner, just LLM analysis.
    """
    logger.info("NODE ENTERED: qa_planner")
    from agent.qa_planner import QAPlannerAgent
 
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "QA Planner")
    updated_task = await QAPlannerAgent().run(task)
    state["task"] = updated_task
    return state
 
 
async def node_assign_parallel_developers(state: GraphState) -> list[Send]:
    """
    Fan-out node for the Module path.
    Reads state['task'].tasks_to_build (populated by Manager agent)
    and emits one `Send('parallel_developer', ...)` per sub-task.
    Each Send carries an isolated GraphState copy so developers don't share state.
    Returns a list of Send objects — LangGraph executes them in parallel.
    """
    logger.info("NODE ENTERED: assign_parallel_developers")
    task = state["task"]
 
    if not task.tasks_to_build:
        logger.warning("assign_parallel_developers: tasks_to_build is empty, skipping fan-out")
        return []
 
    sends: list[Send] = []
    for sub_task in task.tasks_to_build:
        sub_state = task.model_copy(deep=True)
        sub_state.title = sub_task.title
        sub_state.description = sub_task.description
        sub_state.branch = sub_task.branch           # feature/<slug>
        sub_state.acceptance_criteria = sub_task.acceptance_criteria
        sub_state.current_sub_task_id = sub_task.id
 
        sends.append(Send("parallel_developer", {"task": sub_state, "events": [], "pull_requests": []}))
 
    await _emit(
        state,
        f"Dispatching {len(sends)} parallel developer agents",
        event_type="info",
        payload={"sub_task_count": len(sends)},
    )
    return sends
 
 
async def node_parallel_developer(state: GraphState) -> dict[str, list[PullRequestSummary]]:
    """
    Parallel developer node. Runs inside an isolated LangGraph branch.
    Identical to node_run_developer but appends PullRequestSummary to
    state['pull_requests'] instead of writing to state['task'].pr_number.
    """
    logger.info("NODE ENTERED: parallel_developer")
    from agent.developer import DeveloperAgent
 
    task = state["task"]
    await _set_status(state, TaskStatus.PARALLEL_DEV, "Developer")
    updated_task = await DeveloperAgent().run(task)
 
    if updated_task.dev_output and updated_task.dev_output.pr_number:
        pr_summary = PullRequestSummary(
            pr_number=updated_task.dev_output.pr_number,
            branch=updated_task.branch,
            title=updated_task.dev_output.summary[:120],
            status="open",
            sub_task_id=task.current_sub_task_id,
        )
        return {"pull_requests": [pr_summary]}
    else:
        return {"pull_requests": []}
 
 
async def node_tech_lead_merge(state: GraphState) -> GraphState:
    """
    Fan-in node. Receives the merged state from all parallel_developer branches.
    state['pull_requests'] is the concatenated list of all PullRequestSummary
    objects (reduced by operator.add).
    Runs TechLeadMergeAgent to open merge PRs sequentially into the base branch.
    Writes merged pull_requests back to state['task'].pull_requests.
    """
    logger.info("NODE ENTERED: tech_lead_merge")
    from agent.tech_lead_merge import TechLeadMergeAgent
 
    task = state["task"]
    await _set_status(state, TaskStatus.MERGING, "Tech Lead")
 
    task.pull_requests = state["pull_requests"]
 
    updated_task = await TechLeadMergeAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_qa_planner(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: qa_planner")
    from agent.qa_planner import QAPlannerAgent

    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "QA Planner")
    updated_task = await QAPlannerAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_developer(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: developer")
    from agent.developer import DeveloperAgent

    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "Developer")
    updated_task = await DeveloperAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_qa(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: qa")
    from agent.qa import QAAgent

    task = state["task"]
    await _set_status(state, TaskStatus.QA_REVIEW, "QA")
    updated_task = await QAAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_ciso(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: ciso")
    from agent.ciso import CISOAgent

    task = state["task"]
    await _set_status(state, TaskStatus.SECURITY_REVIEW, "CISO")
    updated_task = await CISOAgent().run(task)
    state["task"] = updated_task
    return state


async def node_run_critic(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: critic")
    from agent.critic import CriticAgent

    task = state["task"]
    await _set_status(state, TaskStatus.CRITIC_REVIEW, "Critic")
    updated_task = await CriticAgent().run(task)
    state["task"] = updated_task
    return state


async def node_escalate_human(state: GraphState) -> GraphState:
    """Block the task and write an EscalationRow to Postgres."""
    logger.info("NODE ENTERED: escalate_human")
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
    logger.info("NODE ENTERED: deploy")
    from agent.devops import DevOpsAgent

    task = state["task"]
    await _set_status(state, TaskStatus.AWAITING_DEPLOY, "DevOps")
    updated_task = await DevOpsAgent().run(task)
    state["task"] = updated_task
    return state


async def node_write_memory(state: GraphState) -> GraphState:
    """Extract lessons from completed task and store in Qdrant + Postgres."""
    logger.info("NODE ENTERED: write_memory")
    from database import async_session_maker
    from models.db import MemoryEntryRow
    from memory.long_term import store_memory
    from models.schemas import MemoryEntry
    import uuid
    from datetime import datetime

    task = state["task"]
    await _set_status(state, TaskStatus.DEPLOYED, "Orchestrator")
    await _emit(state, "Writing lessons to long-term memory...")

    lessons: list[str] = []

    # Successful lifecycle lessons
    if task.status == TaskStatus.DEPLOYED:
        lessons.append(f"Successfully implemented {task.title}: {task.description[:100]}...")
    
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

    if not lessons and task.status == TaskStatus.FAILED:
        lessons.append(f"Task '{task.title}' failed. Last error: {task.last_error}")

    tags = ["task-lifecycle", task.repo.split("/")[-1]]
    if task.status == TaskStatus.DEPLOYED:
        tags.append("success")
    elif task.status == TaskStatus.FAILED:
        tags.append("failure")

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
                created_at=datetime.utcnow()
            )
            session.add(row)
            await session.commit()

    await _emit(
        state,
        f"{len(lessons)} lessons stored to memory",
        event_type="success",
        payload={"count": len(lessons)}
    )
    return state


async def node_terminate(state: GraphState) -> GraphState:
    """Final cleanup node for aborted or failed tasks."""
    logger.info("NODE ENTERED: terminate")
    task = state["task"]
    
    # If the task failed/aborted but we still want to capture lessons
    if task.status in (TaskStatus.FAILED, TaskStatus.ESCALATED):
        await node_write_memory(state)
        
    return state


async def node_run_ceo(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: ceo")
    from agent.ceo import CEOAgent
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "CEO/Manager")
    updated = await CEOAgent().run(task)
    updated.ceo_approved = updated.ceo_output.approved if updated.ceo_output else True
    state["task"] = updated
    return state


async def node_run_cto(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: cto")
    from agent.cto import CTOAgent
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "CEO/Manager")
    updated = await CTOAgent().run(task)
    state["task"] = updated
    return state


async def node_run_manager(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: manager")
    from agent.manager import ManagerAgent
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "CEO/Manager")
    updated = await ManagerAgent().run(task)
 
    # Propagate sub_tasks into tasks_to_build for fan-out node.
    if updated.manager_output and updated.manager_output.sub_tasks:
        updated.tasks_to_build = updated.manager_output.sub_tasks
 
    state["task"] = updated
    return state


async def node_run_team_leader(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: team_leader")
    from agent.team_leader import TeamLeaderAgent
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "CEO/Manager")
    updated = await TeamLeaderAgent().run(task)
    state["task"] = updated
    return state


async def node_run_tl_review(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: tl_review")
    from agent.team_leader import TeamLeaderAgent
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "CEO/Manager")
    updated = await TeamLeaderAgent().run_review(task)
    state["task"] = updated
    return state


async def node_run_tl_final(state: GraphState) -> GraphState:
    logger.info("NODE ENTERED: tl_final")
    from agent.team_leader import TeamLeaderAgent
    task = state["task"]
    await _set_status(state, TaskStatus.RUNNING, "CEO/Manager")
    updated = await TeamLeaderAgent().run_final(task)
    state["task"] = updated
    return state


_builder = StateGraph(GraphState)

# Node registration
_builder.add_node("route_request",               node_route_request)
_builder.add_node("load_memory",                 node_load_memory)
_builder.add_node("qa_planner",                  node_qa_planner)
_builder.add_node("ceo",                         node_run_ceo)
_builder.add_node("cto",                         node_run_cto)
_builder.add_node("manager",                     node_run_manager)
_builder.add_node("team_leader",                 node_run_team_leader)
_builder.add_node("tl_review",                   node_run_tl_review)
_builder.add_node("tl_final",                    node_run_tl_final)
_builder.add_node("parallel_developer",          node_parallel_developer)
_builder.add_node("tech_lead_merge",             node_tech_lead_merge)
_builder.add_node("developer",                   node_run_developer)
_builder.add_node("qa",                          node_run_qa)
_builder.add_node("ciso",                        node_run_ciso)
_builder.add_node("critic",                      node_run_critic)
_builder.add_node("escalate_human",              node_escalate_human)
_builder.add_node("deploy",                      node_deploy)
_builder.add_node("write_memory",                node_write_memory)

# Entry point
_builder.set_entry_point("route_request")

# Y-Intersection split
_builder.add_conditional_edges("route_request", route_by_request_type, {
    "load_memory": "load_memory",
    "qa_planner": "qa_planner",
})

# MODULE path: C-suite chain
_builder.add_edge("load_memory", "ceo")
_builder.add_conditional_edges("ceo", route_after_ceo, {
    "cto": "cto",
    "escalate_human": "escalate_human",
})
_builder.add_edge("cto", "manager")
_builder.add_conditional_edges("manager", node_assign_parallel_developers, ["parallel_developer"])

# MODULE path: parallel fan-out
_builder.add_edge("parallel_developer", "tech_lead_merge")

# MODULE path: merge + QA
_builder.add_conditional_edges("tech_lead_merge", route_after_tech_lead_merge, {
    "qa": "qa",
    "escalate_human": "escalate_human",
})

# TASK path: sequential TDD loop
_builder.add_edge("qa_planner", "developer")
_builder.add_edge("developer", "tl_review")
_builder.add_conditional_edges("tl_review", route_after_tl_review, {
    "qa": "qa",
    "developer": "developer",
    "escalate_human": "escalate_human",
})

# Shared QA -> CISO -> Critic -> Deploy path
_builder.add_conditional_edges("qa", route_after_qa, {
    "ciso": "ciso",
    "developer": "developer",
    "critic": "critic",
    "escalate_human": "escalate_human",
})
_builder.add_conditional_edges("ciso", route_after_ciso, {
    "deploy": "deploy",
    "developer": "developer",
    "escalate_human": "escalate_human",
})
_builder.add_conditional_edges("critic", route_after_critic, {
    "developer": "developer",
    "deploy": "deploy",
    "escalate_human": "escalate_human",
})

# Terminal edges
_builder.add_edge("escalate_human", END)
_builder.add_edge("deploy", "tl_final")
_builder.add_conditional_edges("tl_final", route_after_tl_final, {
    "write_memory": "write_memory",
    "developer": "developer",
    "escalate_human": "escalate_human",
})
_builder.add_edge("write_memory", END)

graph = _builder.compile()
