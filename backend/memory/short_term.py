import asyncio
import json
from collections.abc import AsyncGenerator

import redis.asyncio as redis
from pydantic import BaseModel

from config import settings
from models.events import AgentEvent, TaskStatusEvent
from models.schemas import TaskState


STATE_TTL_SECONDS = 7 * 24 * 60 * 60
STATE_KEY_PREFIX = "task_state"
EVENT_CHANNEL_PREFIX = "task_events"

_redis_client: redis.Redis | None = None


def _state_key(task_id: str) -> str:
    return f"{STATE_KEY_PREFIX}:{task_id}"


def _event_channel(task_id: str) -> str:
    return f"{EVENT_CHANNEL_PREFIX}:{task_id}"


async def get_redis() -> redis.Redis:
    global _redis_client

    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )

    return _redis_client


async def save_state(state: TaskState) -> None:
    client = await get_redis()
    await client.set(
        _state_key(state.task_id),
        state.model_dump_json(),
        ex=STATE_TTL_SECONDS,
    )


async def get_state(task_id: str) -> TaskState | None:
    client = await get_redis()
    payload = await client.get(_state_key(task_id))

    if payload is None:
        return None

    return TaskState.model_validate_json(payload)


async def delete_state(task_id: str) -> None:
    client = await get_redis()
    await client.delete(_state_key(task_id))


async def publish_event(
    task_id: str,
    event: AgentEvent | TaskStatusEvent | BaseModel | dict | str,
) -> None:
    client = await get_redis()

    if hasattr(event, "to_sse"):
        payload = event.to_sse()
    elif isinstance(event, BaseModel):
        payload = event.model_dump_json(by_alias=True)
    elif isinstance(event, dict):
        payload = json.dumps(event)
    else:
        payload = str(event)

    await client.publish(_event_channel(task_id), payload)


async def subscribe_events(task_id: str) -> AsyncGenerator[str, None]:
    client = await get_redis()
    pubsub = client.pubsub()
    channel = _event_channel(task_id)
    await pubsub.subscribe(channel)

    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )

            if message and message.get("type") == "message":
                data = message.get("data")
                if data is not None:
                    yield str(data)
                continue

            await asyncio.sleep(0.1)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
