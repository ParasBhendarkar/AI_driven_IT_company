from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session_maker
from memory.short_term import save_state, get_state, publish_event
from models.db import EscalationRow, Task as TaskRow
from models.schemas import TaskStatus, TaskState
from models.events import AgentEvent
from workers.task_worker import run_task


async def get_inbox() -> list[dict]:
    """Return all unresolved escalations with task info."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(EscalationRow, TaskRow)
            .join(TaskRow, EscalationRow.task_id == TaskRow.id)
            .where(EscalationRow.resolved == False)
            .order_by(EscalationRow.created_at.desc())
        )
        rows = result.all()

    inbox = []
    for esc, task in rows:
        inbox.append(
            {
                "id": esc.id,
                "taskId": esc.task_id,
                "taskTitle": task.title,
                "type": esc.escalation_type,
                "reason": esc.reason,
                "recommendation": esc.recommendation,
                "findings": esc.findings,
                "createdAt": esc.created_at.isoformat(),
            }
        )
    return inbox


async def apply_override(task_id: str, instruction: str) -> dict:
    """
    Inject human override instruction into TaskState, reset retry count,
    mark escalation resolved, re-enqueue to Celery.
    """
    state = await get_state(task_id)
    if state is None:
        raise ValueError(f"Task {task_id} not found in Redis")

    state.human_override = instruction
    state.retry_count = 0
    state.status = TaskStatus.PENDING
    state.last_error = None
    state.updated_at = datetime.utcnow()
    await save_state(state)

    async with async_session_maker() as session:
        result = await session.execute(
            select(EscalationRow)
            .where(EscalationRow.task_id == task_id)
            .where(EscalationRow.resolved == False)
            .order_by(EscalationRow.created_at.desc())
        )
        esc = result.scalar_one_or_none()
        if esc:
            esc.resolved = True
            esc.resolved_at = datetime.utcnow()
            esc.human_override_text = instruction if hasattr(esc, "human_override_text") else None
            await session.commit()

    await publish_event(
        task_id,
        AgentEvent(
            task_id=task_id,
            agent="Orchestrator",
            description="Human override received — resuming task",
            type="info",
            payload={"instruction": instruction},
        ),
    )

    run_task.delay(task_id)

    return {"status": "resumed", "task_id": task_id}
