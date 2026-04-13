from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session_maker
from models.db import Task as TaskRow, AgentCall, MemoryEntryRow, EscalationRow


async def get_activity(filter_status: str = "All", limit: int = 50) -> list[dict]:
    async with async_session_maker() as session:
        query = select(TaskRow).order_by(TaskRow.created_at.desc()).limit(limit)
        if filter_status != "All":
            query = query.where(TaskRow.status == filter_status.lower())

        result = await session.execute(query)
        tasks = result.scalars().all()

        activity = []
        for task in tasks:
            agents_result = await session.execute(
                select(AgentCall.agent_role).where(AgentCall.task_id == task.id).distinct()
            )
            agent_roles = [r[0] for r in agents_result.all()]

            activity.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "description": _outcome_description(task),
                    "agents": agent_roles or [task.current_agent],
                    "time": _relative_time(task.created_at),
                    "type": _event_type(task.status),
                }
            )

    return activity


async def get_stats() -> dict:
    async with async_session_maker() as session:
        week_ago = datetime.utcnow() - timedelta(days=7)

        tasks_week = await session.scalar(select(func.count(TaskRow.id)).where(TaskRow.created_at >= week_ago)) or 0

        avg_retries = await session.scalar(
            select(func.avg(TaskRow.retry_count)).where(TaskRow.created_at >= week_ago)
        ) or 0.0

        ciso_blocks = await session.scalar(
            select(func.count(EscalationRow.id))
            .where(EscalationRow.escalation_type == "security_block")
            .where(EscalationRow.created_at >= week_ago)
        ) or 0

        memory_writes = await session.scalar(
            select(func.count(MemoryEntryRow.id)).where(MemoryEntryRow.created_at >= week_ago)
        ) or 0

        chart_data = []
        for i in range(6, -1, -1):
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)

            completed = await session.scalar(
                select(func.count(TaskRow.id))
                .where(TaskRow.created_at >= day_start)
                .where(TaskRow.created_at < day_end)
                .where(TaskRow.status == "deployed")
            ) or 0

            escalated = await session.scalar(
                select(func.count(TaskRow.id))
                .where(TaskRow.created_at >= day_start)
                .where(TaskRow.created_at < day_end)
                .where(TaskRow.status == "escalated")
            ) or 0

            chart_data.append(
                {
                    "day": day_start.strftime("%a"),
                    "completed": completed,
                    "escalated": escalated,
                }
            )

    return {
        "tasksThisWeek": tasks_week,
        "avgRetries": round(float(avg_retries), 1),
        "cisoBlocks": ciso_blocks,
        "memoryWrites": memory_writes,
        "chartData": chart_data,
    }


def _outcome_description(task: TaskRow) -> str:
    s = task.status
    if s == "deployed":
        return f"Deployed after {task.retry_count} retries"
    if s == "escalated":
        return f"Escalated to human after {task.retry_count} attempts"
    if s == "blocked":
        return "CISO security block — awaiting fix"
    if s == "failed":
        return "Task failed"
    return f"Status: {s}"


def _relative_time(dt: datetime) -> str:
    delta = datetime.utcnow() - dt.replace(tzinfo=None)
    s = int(delta.total_seconds())
    if s < 60:
        return f"{s}s ago"
    if s < 3600:
        return f"{s//60}m ago"
    if s < 86400:
        return f"{s//3600}h ago"
    return f"{s//86400}d ago"


def _event_type(status: str) -> str:
    if status == "deployed":
        return "success"
    if status in ("failed", "escalated"):
        return "error"
    if status == "blocked":
        return "warning"
    return "info"
