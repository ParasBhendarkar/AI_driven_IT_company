from __future__ import annotations

import json
import logging
import time
from datetime import datetime

from agent.base import BaseAgent
from config import settings
from core.retry import build_retry_context
from models.schemas import TaskState, TaskStatus, DevOutput, FileChange
from tools.github_tool import GitHubTool

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 15


class DeveloperAgent(BaseAgent):
    role = "Developer"
    model = "claude-sonnet-4-5"

    SYSTEM_PROMPT = """
You are an expert software developer agent inside an autonomous AI company system.

You receive a task description with acceptance criteria, the target GitHub repo
and branch, optionally QA failure reports (when retrying), memory hints from
past similar tasks, and optionally a human override instruction.

Your job:
1. Call read_file to understand existing code before writing anything.
2. Call create_or_update_file to write or fix files.
3. Always call open_pull_request after all file changes are complete.

Rules:
- When retrying: fix ONLY the reported QA failures. Do not refactor other code.
- When a human override instruction is present: follow it exactly — it is highest priority.
- Read before you write. Never assume file contents.
- One open_pull_request call ends your turn.
- Output tool calls only. No prose explanations.
"""

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file from the GitHub repository branch.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to repo root, e.g. src/api/anomaly.py",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_or_update_file",
                "description": "Create or update a file in the repository on the task branch.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to repo root"},
                        "content": {"type": "string", "description": "Full file content"},
                        "message": {"type": "string", "description": "Git commit message"},
                    },
                    "required": ["path", "content", "message"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_pull_request",
                "description": "Open a pull request. Call this after all file changes are complete.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "body": {"type": "string", "description": "PR description with summary of changes"},
                    },
                    "required": ["title", "body"],
                },
            },
        },
    ]

    async def run(self, state: TaskState) -> TaskState:
        start = time.time()
        await self._publish(state.task_id, "Reading repository and planning changes...")

        gh = GitHubTool(
            repo=state.repo,
            branch=state.branch,
            access_token=settings.GITHUB_TOKEN,
        )
        await gh.ensure_branch_exists()

        messages = [{"role": "user", "content": self._build_prompt(state)}]
        file_changes: list[FileChange] = []
        pr_number: int | None = None
        pr_url: str | None = None
        commit_sha: str | None = None
        tokens_total: int = 0
        pr_opened = False

        for iteration in range(MAX_TOOL_ITERATIONS):
            response = await self._call_llm(
                messages=messages,
                tools=self.TOOLS,
                system=self.SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=4096,
            )

            tokens_total += response.usage.total_tokens if response.usage else 0

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            message = choice.message

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in (message.tool_calls or [])
                    ]
                    or None,
                }
            )

            if finish_reason == "stop" or not message.tool_calls:
                break

            tool_results = []
            for tc in message.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                result_content = ""

                if name == "read_file":
                    path = args.get("path", "")
                    content = await gh.read_file(path)
                    result_content = content or f"File not found: {path}"
                    await self._publish(
                        state.task_id,
                        f"Read file: {path}",
                    )

                elif name == "create_or_update_file":
                    path = args.get("path", "")
                    content = args.get("content", "")
                    msg = args.get("message", f"chore: update {path}")
                    result = await gh.create_or_update_file(path, content, msg)
                    commit_sha = result.get("commit_sha")
                    file_changes.append(
                        FileChange(
                            file_path=path,
                            change_type="modify",
                            summary=msg,
                            patch=None,
                        )
                    )
                    result_content = f"File written: {path} (commit {commit_sha})"
                    await self._publish(
                        state.task_id,
                        f"Wrote {path} — {msg}",
                        payload={"path": path, "commit_sha": commit_sha},
                    )

                elif name == "open_pull_request":
                    title = args.get("title", f"feat: {state.title}")
                    body = args.get("body", "")
                    result = await gh.open_pull_request(title, body)
                    pr_number = result.get("number")
                    pr_url = result.get("url")
                    pr_opened = True
                    result_content = f"PR #{pr_number} opened: {pr_url}"
                    await self._publish(
                        state.task_id,
                        f"PR #{pr_number} opened: {title}",
                        event_type="success",
                        payload={"pr_number": pr_number, "pr_url": pr_url},
                    )

                else:
                    result_content = f"Unknown tool: {name}"

                tool_results.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_content,
                    }
                )

            messages.extend(tool_results)

            if pr_opened:
                break

        summary = (
            f"PR #{pr_number} opened with {len(file_changes)} file(s) changed"
            if pr_opened
            else f"Completed {len(file_changes)} file change(s) without opening PR"
        )

        dev_output = DevOutput(
            summary=summary,
            branch=state.branch,
            commit_hash=commit_sha,
            pr_number=pr_number,
            files_changed=file_changes,
        )

        state.dev_output = dev_output
        state.pr_number = pr_number
        state.commit_hash = commit_sha

        latency = time.time() - start

        await self._log_call(
            task_id=state.task_id,
            action="developer_run",
            input_payload={"prompt_length": len(messages[0]["content"])},
            output_payload={"pr_number": pr_number, "files_changed": len(file_changes)},
            tokens_used=tokens_total,
            latency_seconds=latency,
        )

        await self._publish(
            state.task_id,
            summary,
            event_type="success" if pr_opened else "warning",
        )

        return state

    def _build_prompt(self, state: TaskState) -> str:
        lines = [
            f"Task: {state.title}",
            f"Description: {state.description}",
            f"Repository: {state.repo}",
            f"Branch: {state.branch}",
            "",
            "Acceptance criteria:",
        ]
        for criterion in (state.acceptance_criteria or []):
            lines.append(f"  - {criterion}")

        if state.qa_result and state.retry_count > 0:
            lines.append("")
            lines.append(build_retry_context(state.qa_result, state.memory_hits or []))

        if state.critic_output:
            root_cause = getattr(
                state.critic_output,
                "root_cause",
                getattr(state.critic_output, "summary", ""),
            )
            fix = getattr(
                state.critic_output,
                "fix",
                getattr(state.critic_output, "recommendation", ""),
            )
            lines.append("")
            lines.append("--- CRITIC ROOT CAUSE ANALYSIS ---")
            lines.append(f"Root cause: {root_cause}")
            lines.append(f"Suggested fix: {fix}")

        elif state.memory_hits and state.retry_count == 0:
            lines.append("")
            lines.append("--- RELEVANT PAST KNOWLEDGE ---")
            for hit in state.memory_hits:
                score = hit.get("score", 0)
                content = hit.get("content", "")
                lines.append(f"[{score:.0%}] {content}")

        if state.human_override:
            lines.append("")
            lines.append("═══ HUMAN OVERRIDE INSTRUCTION (HIGHEST PRIORITY) ═══")
            lines.append(state.human_override)
            lines.append("Follow this instruction exactly. It supersedes everything above.")

        return "\n".join(lines)
