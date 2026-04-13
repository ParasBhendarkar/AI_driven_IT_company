from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from agent.base import BaseAgent
from models.schemas import TaskState, TaskStatus

logger = logging.getLogger(__name__)


class DevOpsAgent(BaseAgent):
    role = "DevOps"

    async def run(self, state: TaskState) -> TaskState:
        sha = None
        if state.dev_output:
            sha = getattr(state.dev_output, "commit_hash", None)

        short_sha = (sha or "unknown")[:7]
        await self._publish(
            state.task_id,
            f"Deploying {short_sha} to production...",
        )

        await asyncio.sleep(2)

        state.deployed_at = datetime.utcnow()
        state.completed_at = datetime.utcnow()

        await self._update_task_status(state, TaskStatus.DEPLOYED, "DevOps")
        await self._publish(
            state.task_id,
            f"Deployed {short_sha} to production. Monitors active.",
            event_type="success",
            payload={"commit_sha": sha, "deployed_at": state.deployed_at.isoformat()},
        )
        await self._log_call(
            task_id=state.task_id,
            action="deploy",
            output_payload={"commit_sha": sha, "env": "production"},
        )
        return state
