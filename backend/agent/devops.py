from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from agent.base import BaseAgent
from config import settings
from memory.short_term import get_task_token
from models.schemas import TaskState, TaskStatus
from tools.github_tool import GitHubTool

logger = logging.getLogger(__name__)


class DevOpsAgent(BaseAgent):
    role = "DevOps"
    model = "ollama/qwen2.5-coder:3b"

    async def run(self, state: TaskState) -> TaskState:
        await self._publish(
            state.task_id,
            "Deploying changes to GitHub...",
        )

        try:
            access_token = await get_task_token(state.task_id) or settings.GITHUB_TOKEN
            if not access_token:
                raise RuntimeError("Missing GitHub token for DevOps agent")

            gh = GitHubTool(
                repo=state.repo,
                branch=state.branch,
                access_token=access_token,
            )
            await gh.ensure_branch_exists()
            base_branch = await asyncio.to_thread(lambda: gh.repo.default_branch)

            commit_sha = None
            pr_number = None

            if state.reviewed_file_contents:
                commit_message = getattr(state.dev_output, "commit_message", None) or f"Commit for task {state.title}"
                for path, content in state.reviewed_file_contents.items():
                    result = await gh.create_or_update_file(
                        path,
                        content,
                        commit_message,
                    )
                    commit_sha = result.get("commit_sha")

                if state.branch != base_branch:
                    pr_title = getattr(state.dev_output, "pr_title", None) or f"Task {state.title}"
                    pr_body = getattr(state.dev_output, "pr_body", None) or getattr(state, "description", "")
                    pr_result = await gh.open_pull_request(
                        title=pr_title,
                        body=pr_body,
                        base=base_branch,
                    )
                    pr_number = pr_result.get("number")
                    
                    if pr_number is not None and pr_result is not None:
                        await self._publish(
                            state.task_id,
                            f"PR #{pr_number} opened by DevOps: {pr_title}",
                            event_type="success",
                            payload={"pr_number": pr_number, "pr_url": pr_result.get("url")},
                        )

            if state.dev_output:
                state.dev_output.commit_hash = commit_sha
                state.dev_output.pr_number = pr_number

            state.commit_hash = commit_sha
            state.pr_number = pr_number

            short_sha = (commit_sha or "none")[:7]

            state.deployed_at = datetime.utcnow()
            state.completed_at = datetime.utcnow()

            await self._update_task_status(state, TaskStatus.DEPLOYED, "DevOps")
            await self._publish(
                state.task_id,
                f"Deployed {short_sha} to production. Monitors active.",
                event_type="success",
                payload={"commit_sha": commit_sha, "deployed_at": state.deployed_at.isoformat()},
            )
            await self._log_call(
                task_id=state.task_id,
                action="deploy",
                output_payload={"commit_sha": commit_sha, "pr_number": pr_number, "env": "production"},
            )
        except Exception as exc:
            logger.error(f"DevOps deployment failed: {exc}")
            state.last_error = str(exc)
            await self._publish(
                state.task_id,
                f"Deployment failed: {exc}",
                event_type="error",
            )
            
        return state
