from __future__ import annotations

import asyncio
import logging

from workers.celery_app import celery_app
from memory.short_term import get_state, save_state, publish_event
from models.schemas import TaskStatus
from models.events import AgentEvent

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=0,
    name="conductor.run_task",
)
def run_task(self, task_id: str) -> dict:
    """
    Celery entry point. Dequeues a task_id, loads TaskState from Redis,
    runs the LangGraph graph, returns final status.
    """
    return asyncio.run(_run_task_async(task_id))


async def _run_task_async(task_id: str) -> dict:
    from core.graph import graph

    logger.info("Worker starting task %s", task_id)

    state = await get_state(task_id)
    if state is None:
        logger.warning("Task %s not found in Redis, rebuilding from Postgres", task_id)
        state = await _rebuild_state_from_postgres(task_id)
        if state is None:
            logger.error("Task %s not found in Redis or Postgres", task_id)
            return {"status": "error", "task_id": task_id, "error": "State not found"}
        await save_state(state)

    try:
        from datetime import datetime
        from database import async_session_maker
        from sqlalchemy import update
        from models.db import Task as TaskRow

        async with async_session_maker() as session:
            await session.execute(
                update(TaskRow).where(TaskRow.id == task_id).values(started_at=datetime.utcnow(), status="running")
            )
            await session.commit()
    except Exception as exc:
        logger.warning("Could not update started_at: %s", exc)

    graph_state = {"task": state, "events": []}

    try:
        final_state = await graph.ainvoke(graph_state)
        final_task = final_state["task"]

        from database import async_session_maker
        from sqlalchemy import update
        from models.db import Task as TaskRow
        from datetime import datetime

        async with async_session_maker() as session:
            await session.execute(
                update(TaskRow)
                .where(TaskRow.id == task_id)
                .values(
                    status=final_task.status.value,
                    progress=final_task.progress,
                    pr_number=final_task.pr_number,
                    commit_hash=final_task.commit_hash,
                    dev_output=final_task.dev_output.model_dump() if final_task.dev_output else None,
                    qa_result=final_task.qa_result.model_dump() if final_task.qa_result else None,
                    ciso_gate=final_task.ciso_gate.model_dump() if final_task.ciso_gate else None,
                    critic_output=final_task.critic_output.model_dump() if final_task.critic_output else None,
                    completed_at=datetime.utcnow()
                    if final_task.status in (TaskStatus.DEPLOYED, TaskStatus.FAILED, TaskStatus.ESCALATED)
                    else None,
                )
            )
            await session.commit()

        logger.info("Task %s completed with status %s", task_id, final_task.status)
        return {"status": final_task.status.value, "task_id": task_id}

    except Exception as exc:
        logger.exception("Task %s failed with unhandled exception", task_id)

        err = str(exc) or repr(exc)

        state.status = TaskStatus.FAILED
        state.progress = 0
        state.last_error = err
        await save_state(state)

        # Persist failure to Postgres so Dashboard (DB-backed) matches TaskDetail (Redis-backed)
        try:
            from datetime import datetime
            from database import async_session_maker
            from sqlalchemy import update
            from models.db import Task as TaskRow

            async with async_session_maker() as session:
                await session.execute(
                    update(TaskRow)
                    .where(TaskRow.id == task_id)
                    .values(
                        status=TaskStatus.FAILED.value,
                        progress=0,
                        current_agent=str(getattr(state.current_agent, "value", state.current_agent)),
                        completed_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                    )
                )
                await session.commit()
        except Exception as db_exc:
            logger.warning("Could not persist failure to Postgres for task %s: %s", task_id, db_exc)

        await publish_event(
            task_id,
            AgentEvent(
                task_id=task_id,
                agent="Orchestrator",
                description=f"Task failed: {err}",
                type="error",
            ),
        )
        return {"status": "failed", "task_id": task_id, "error": err}


async def _rebuild_state_from_postgres(task_id: str):
    from database import async_session_maker
    from models.db import Task as TaskRow
    from models.schemas import Priority, TaskState
    from sqlalchemy import select

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
        priority=Priority(row.priority),
        acceptance_criteria=row.acceptance_criteria or [],
        context_refs=row.context_refs or [],
        status=TaskStatus(row.status),
        current_agent=row.current_agent or "Orchestrator",
        retry_count=row.retry_count or 0,
        progress=row.progress or 5,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
