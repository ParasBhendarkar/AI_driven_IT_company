from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime

import litellm

from config import settings
from database import async_session_maker
from memory.short_term import save_state, publish_event
from models.db import AgentCall
from models.events import AgentEvent, TaskStatusEvent
from models.schemas import TaskState, TaskStatus
from core.graph import _compute_progress

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    role: str = "BaseAgent"
    model: str = "ollama/phi3.5"

    @abstractmethod
    async def run(self, state: TaskState) -> TaskState:
        """Execute agent logic. Receive state, return updated state."""
        ...

    async def _call_llm(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_seconds: int = 180,
        json_mode: bool = False,
    ) -> litellm.ModelResponse | None:
        """
        Async LLM call via LiteLLM.
        Prepends system message if provided.
        Passes tools if model supports tool_use.
        Returns None (never raises) so graph nodes can detect failure and continue.
        """
        logger.info(f"LLM call starting — role={self.role}, model={self.model}")

        try:
            if system:
                messages = [{"role": "system", "content": system}] + messages

            kwargs: dict = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout": timeout_seconds,
            }
            if self.model.startswith("ollama/"):
                kwargs["api_base"] = settings.OLLAMA_BASE_URL

            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            if json_mode:
                kwargs["format"] = "json"

            response = await asyncio.wait_for(
                litellm.acompletion(**kwargs),
                timeout=timeout_seconds,
            )

            tokens_used = response.usage.total_tokens if response and response.usage else 0
            logger.info(f"LLM call finished — role={self.role}, tokens={tokens_used}")
            return response

        except asyncio.TimeoutError:
            logger.error(
                f"LLM call timed out — role={self.role}, model={self.model}, "
                f"timeout={timeout_seconds}s"
            )
            return None
        except Exception as exc:
            logger.error(
                f"LLM call failed — role={self.role}, model={self.model}, "
                f"error_type={type(exc).__name__}, error={exc}"
            )
            return None

    async def _publish(
        self,
        task_id: str,
        description: str,
        event_type: str = "info",
        payload: dict | None = None,
        agent: str | None = None,
    ) -> None:
        """Publish AgentEvent to Redis pub/sub -> SSE stream -> LiveFeed.tsx."""
        event = AgentEvent(
            task_id=task_id,
            agent=agent or self.role,
            description=description,
            type=event_type,
            payload=payload,
        )
        await publish_event(task_id, event)

    async def _update_task_status(
        self,
        state: TaskState,
        status: TaskStatus,
        agent: str | None = None,
    ) -> TaskState:
        """
        Set state.status + current_agent + progress.
        Saves to Redis. Publishes TaskStatusEvent so Dashboard card updates.
        Returns updated state.
        """
        state.status = status
        state.current_agent = agent or self.role
        state.updated_at = datetime.utcnow()
        state.progress = _compute_progress(status)
        await save_state(state)
        await publish_event(
            state.task_id,
            TaskStatusEvent(
                task_id=state.task_id,
                status=status.value,
                current_agent=agent or self.role,
                retry_count=state.retry_count,
                progress=state.progress,
            ),
        )
        return state

    async def _log_call(
        self,
        task_id: str,
        action: str,
        input_payload: dict | None = None,
        output_payload: dict | None = None,
        tokens_used: int = 0,
        latency_seconds: float = 0.0,
        cost_usd: float = 0.0,
        error_message: str | None = None,
        status: str = "completed",
    ) -> None:
        """
        Write AgentCall row to Postgres.
        Powers the AgentLog screen in the frontend.
        """
        import uuid

        async with async_session_maker() as session:
            row = AgentCall(
                id=str(uuid.uuid4()),
                task_id=task_id,
                agent_role=self.role,
                action=action,
                input_payload=input_payload,
                output_payload=output_payload,
                tokens_used=tokens_used,
                latency_seconds=latency_seconds,
                cost_usd=cost_usd,
                error_message=error_message,
                status=status,
            )
            session.add(row)
            await session.commit()
