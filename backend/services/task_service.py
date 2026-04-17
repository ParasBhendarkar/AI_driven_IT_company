from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import async_session_maker
from memory.short_term import save_state, get_state, save_task_token
from models.db import Task as TaskRow
from models.schemas import TaskCreate, TaskState, TaskStatus, TaskListItem, Priority, AgentRole, RequestType, SubTask, PullRequestSummary
from workers.task_worker import run_task


def _slugify(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:50].strip("-")


def _compute_progress(status: TaskStatus) -> int:
    mapping = {
        TaskStatus.PENDING: 5,
        TaskStatus.RUNNING: 20,
        TaskStatus.RETRYING: 35,
        TaskStatus.QA_REVIEW: 50,
        TaskStatus.SECURITY_REVIEW: 70,
        TaskStatus.CRITIC_REVIEW: 45,
        TaskStatus.AWAITING_DEPLOY: 85,
        TaskStatus.DEPLOYED: 100,
        TaskStatus.FAILED: 0,
        TaskStatus.ESCALATED: 30,
        TaskStatus.BLOCKED: 40,
        TaskStatus.PARALLEL_DEV: 40,
        TaskStatus.MERGING: 75,
    }
    return mapping.get(status, 0)


def _time_elapsed(created_at: datetime) -> str:
    delta = datetime.utcnow() - created_at.replace(tzinfo=None)
    total = int(delta.total_seconds())
    m, s = divmod(total, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def _parse_sub_tasks(raw_sub_tasks) -> list[SubTask]:
    if not raw_sub_tasks:
        return []
    return [SubTask.model_validate(sub_task) for sub_task in raw_sub_tasks]


def _parse_pull_requests(raw_pull_requests) -> list[PullRequestSummary]:
    if not raw_pull_requests:
        return []
    return [PullRequestSummary.model_validate(pr) for pr in raw_pull_requests]


async def create_task(data: TaskCreate, github_token: str) -> TaskState:
    """
    Create TaskState -> save to Redis -> insert Postgres row -> enqueue Celery.
    Returns the TaskState immediately (task runs async in worker).
    """
    task_id = str(uuid.uuid4())
    branch = data.branch or f"feat/{_slugify(data.title)}"

    state = TaskState(
        task_id=task_id,
        title=data.title,
        description=data.description,
        repo=data.repo,
        branch=branch,
        priority=data.priority,
        acceptance_criteria=data.acceptance_criteria,
        context_refs=data.context_refs,
        status=TaskStatus.PENDING,
        current_agent="Orchestrator",
        progress=5,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        request_type=data.request_type,
    )

    await save_state(state)
    await save_task_token(task_id, github_token)

    async with async_session_maker() as session:
        row = TaskRow(
            id=task_id,
            title=data.title,
            description=data.description,
            repo=data.repo,
            branch=branch,
            status=TaskStatus.PENDING.value,
            priority=data.priority.value,
            acceptance_criteria=data.acceptance_criteria,
            context_refs=data.context_refs,
            current_agent="Orchestrator",
            retry_count=0,
            max_retries=5,
            progress=5,
            request_type=data.request_type.value,
        )
        session.add(row)
        await session.commit()

    run_task.delay(task_id)

    return state


async def get_task(task_id: str) -> TaskState | None:
    """Load from Redis first, fallback to Postgres if evicted."""
    state = await get_state(task_id)
    if state:
        state.progress = _compute_progress(state.status)
        return state

    async with async_session_maker() as session:
        result = await session.execute(select(TaskRow).where(TaskRow.id == task_id))
        row = result.scalar_one_or_none()

    if row is None:
        return None

    return TaskState(
        task_id=row.id,
        title=row.title,
        description=row.description,
        repo=row.repo,
        branch=row.branch,
        status=TaskStatus(row.status),
        priority=Priority(row.priority),
        current_agent=row.current_agent or "Orchestrator",
        retry_count=row.retry_count,
        progress=_compute_progress(TaskStatus(row.status)),
        created_at=row.created_at,
        updated_at=row.updated_at,
        request_type=RequestType(row.request_type) if row.request_type else RequestType.TASK,
        tasks_to_build=_parse_sub_tasks(row.sub_tasks),
        pull_requests=_parse_pull_requests(row.pull_requests),
        merge_commit_hash=row.merge_commit_hash,
    )


async def list_tasks() -> list[TaskListItem]:
    """Return lightweight list for Dashboard."""
    async with async_session_maker() as session:
        result = await session.execute(select(TaskRow).order_by(TaskRow.created_at.desc()).limit(50))
        rows = result.scalars().all()

    # Prefer Redis state when available so Dashboard reflects live/most-recent status.
    redis_states = await asyncio.gather(*(get_state(row.id) for row in rows))

    items = []
    for row, state in zip(rows, redis_states):
        status = state.status if state else TaskStatus(row.status)
        items.append(
            TaskListItem(
                id=row.id,
                title=state.title if state else row.title,
                status=status,
                priority=state.priority if state else Priority(row.priority),
                repo=state.repo if state else row.repo,
                branch=state.branch if state else row.branch,
                currentAgent=str(getattr(state.current_agent, "value", state.current_agent))
                if state
                else (row.current_agent or "Orchestrator"),
                retryCount=state.retry_count if state else row.retry_count,
                maxRetries=state.max_retries if state else row.max_retries,
                progress=_compute_progress(status),
                timeElapsed=_time_elapsed(row.created_at),
                prNumber=(state.pr_number if state else row.pr_number),
            )
        )
    return items


async def abort_task(task_id: str) -> None:
    """Mark task as failed, update both Redis and Postgres, and resolve any escalations."""
    state = await get_state(task_id)
    if state:
        state.status = TaskStatus.FAILED
        state.last_error = "Aborted by founder"
        await save_state(state)

    from models.db import EscalationRow
    async with async_session_maker() as session:
        result = await session.execute(select(TaskRow).where(TaskRow.id == task_id))
        row = result.scalar_one_or_none()
        if row:
            row.status = TaskStatus.FAILED.value
            
        esc_result = await session.execute(
            select(EscalationRow)
            .where(EscalationRow.task_id == task_id)
            .where(EscalationRow.resolved == False)
        )
        for esc in esc_result.scalars().all():
            esc.resolved = True
            esc.resolved_at = datetime.utcnow()
            esc.human_override_text = "Aborted by founder"
            
        await session.commit()
