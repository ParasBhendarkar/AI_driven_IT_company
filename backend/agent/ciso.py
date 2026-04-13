from __future__ import annotations

import asyncio
import logging

from agent.base import BaseAgent
from models.schemas import TaskState, TaskStatus, CISOGate

logger = logging.getLogger(__name__)


class CISOAgent(BaseAgent):
    role = "CISO"

    async def run(self, state: TaskState) -> TaskState:
        await self._publish(state.task_id, "Running security scan...")
        await asyncio.sleep(1)

        gate = CISOGate(
            status="approved",
            summary="Phase 1 stub — no findings (Semgrep integrated in Phase 2)",
            findings=[],
            blocked=False,
        )
        state.ciso_gate = gate

        await self._update_task_status(state, TaskStatus.AWAITING_DEPLOY, "CISO")
        await self._publish(
            state.task_id,
            "Security scan passed — no findings",
            event_type="success",
        )
        await self._log_call(
            task_id=state.task_id,
            action="ciso_scan",
            output_payload={"decision": "approve", "findings": 0},
        )
        return state
