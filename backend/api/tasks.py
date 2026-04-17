from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from memory.short_term import subscribe_events
from models.schemas import TaskCreate, TaskState, TaskListItem, OverrideRequest, RequestType
from services.auth_service import extract_bearer_token
from services.task_service import create_task, get_task, list_tasks, abort_task

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Tasks"])

KEEPALIVE_INTERVAL = 15


@router.post("/tasks", response_model=TaskState, status_code=201)
async def create_task_endpoint(
    data: TaskCreate,
    authorization: str | None = Header(default=None),
) -> TaskState:
    token = extract_bearer_token(authorization)
    return await create_task(data, github_token=token)


@router.get("/tasks", response_model=list[TaskListItem])
async def list_tasks_endpoint() -> list[TaskListItem]:
    return await list_tasks()


@router.get("/tasks/{task_id}", response_model=TaskState)
async def get_task_endpoint(task_id: str) -> TaskState:
    state = await get_task(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return state


@router.get("/tasks/{task_id}/stream")
async def stream_task_events(task_id: str) -> StreamingResponse:
    """
    SSE endpoint. Frontend LiveFeed.tsx connects here.
    Streams AgentEvent and TaskStatusEvent JSON as text/event-stream.
    Sends ": ping" keepalive every 15 seconds.
    Cleans up Redis subscription on client disconnect.
    """

    async def event_generator():
        try:
            async for raw_event in subscribe_events(task_id):
                if raw_event.startswith("data:") or raw_event.startswith("event:"):
                    yield raw_event
                else:
                    yield f"data: {raw_event}\n\n"
        except asyncio.CancelledError:
            logger.info("SSE client disconnected from task %s", task_id)
        except GeneratorExit:
            logger.info("SSE generator closed for task %s", task_id)

    async def keepalive_generator():
        """Wrap event_generator with periodic keepalives."""
        import time

        last_ping = time.monotonic()
        async for chunk in event_generator():
            yield chunk
            now = time.monotonic()
            if now - last_ping >= KEEPALIVE_INTERVAL:
                yield ": ping\n\n"
                last_ping = now

    return StreamingResponse(
        keepalive_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tasks/{task_id}/log")
async def get_task_log(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    from sqlalchemy import select
    from models.db import AgentCall

    result = await db.execute(
        select(AgentCall).where(AgentCall.task_id == task_id).order_by(AgentCall.created_at.asc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "agent": row.agent_role,
            "action": row.action,
            "inputPayload": row.input_payload,
            "outputPayload": row.output_payload,
            "tokensUsed": row.tokens_used,
            "latencySeconds": row.latency_seconds,
            "costUsd": row.cost_usd,
            "status": row.status,
            "createdAt": row.created_at.isoformat(),
        }
        for row in rows
    ]
