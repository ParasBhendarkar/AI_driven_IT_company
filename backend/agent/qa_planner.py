from __future__ import annotations

import json
import logging
import time

from agent.base import BaseAgent
from models.schemas import TaskState, TaskStatus

logger = logging.getLogger(__name__)

QA_PLANNER_SYSTEM_PROMPT = """
You are the Senior QA Automation Engineer in an autonomous AI-driven software company.
Your role is to write the automated test suite BEFORE the Developer writes the application code (Test-Driven Development).

INPUTS YOU WILL RECEIVE:
1. The Founder's original request.
2. The CTO's architectural decisions.
3. The Team Leader's Enriched Brief with Acceptance Criteria.

YOUR CRITICAL INSTRUCTIONS:
1. Write a comprehensive `pytest` suite that covers every Acceptance Criterion.
2. Include tests for the "Happy Path", "Edge Cases", and "Failure Modes" (using pytest.raises).
3. Include all necessary imports at the top of the file (e.g., `import pytest`).
4. CRITICAL HANDOFF: You must use the `create_or_update_file` tool to save your generated test code to the repository (e.g., to `test_calculator.py`). 
5. The `QA Runner` agent will execute the file you save here after the Developer finishes their work. Ensure the file is completely ready to run.
"""

class QAPlannerAgent(BaseAgent):
    role = "QA Planner"
    model = "ollama/qwen2.5-coder:3b"

    async def run(self, state: TaskState) -> TaskState:
        logger.info("NODE ENTERED: qa_planner")
        start = time.time()

        try:
            await self._publish(state.task_id, "Planning and writing QA tests via TDD...")

            messages = [{"role": "user", "content": self._build_prompt(state)}]
            
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "create_or_update_file",
                        "description": "Save generated code to the repository",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "The path to the file, e.g., tests/test_feature.py"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "The complete file content"
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "Brief summary of changes"
                                }
                            },
                            "required": ["file_path", "content"]
                        }
                    }
                }
            ]

            response = await self._call_llm(
                messages=messages,
                system=QA_PLANNER_SYSTEM_PROMPT,
                tools=tools,
                temperature=0.1,
                max_tokens=4096,
            )

            if response is None:
                logger.warning("QAPlannerAgent LLM call failed or timed out.")
                return state

            tokens = response.usage.total_tokens if response.usage else 0
            latency = time.time() - start

            message = response.choices[0].message
            files_saved = 0

            if hasattr(message, 'tool_calls') and message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.function.name == "create_or_update_file":
                        try:
                            args = json.loads(tool_call.function.arguments)
                            path = args.get("file_path")
                            content = args.get("content")
                            
                            if path and content:
                                if not hasattr(state, "reviewed_file_contents") or state.reviewed_file_contents is None:
                                    state.reviewed_file_contents = {}
                                state.reviewed_file_contents[path] = content
                                files_saved += 1
                                await self._publish(
                                    state.task_id,
                                    f"Wrote tests to {path}",
                                    payload={"path": path}
                                )
                        except json.JSONDecodeError:
                            logger.error("Failed to parse tool arguments")

            if files_saved == 0 and message.content:
                content = message.content
                import re
                blocks = re.findall(r"```python\n(.*?)\n```", content, re.DOTALL)
                if blocks:
                    path = "tests/test_feature.py"
                    if not hasattr(state, "reviewed_file_contents") or state.reviewed_file_contents is None:
                        state.reviewed_file_contents = {}
                    state.reviewed_file_contents[path] = blocks[0]
                    files_saved += 1
                    await self._publish(state.task_id, f"Wrote fallback tests to {path}")

            await self._log_call(
                task_id=state.task_id,
                action="qa_planner",
                input_payload={"prompt": "TDD Planning"},
                output_payload={"files": files_saved},
                tokens_used=tokens,
                latency_seconds=latency,
            )

            await self._publish(
                state.task_id,
                f"QA Planner completed ({files_saved} test files created)",
                event_type="success",
            )
            return state

        except Exception as exc:
            logger.error(f"QAPlanner run() crashed: {exc}")
            state.last_error = str(exc)
            await self._publish(
                state.task_id,
                f"QA Planner failed: {exc}",
                event_type="error",
            )
            return state

    def _build_prompt(self, state: TaskState) -> str:
        lines = [
            f"Original Request: {state.description}",
            "",
            "Architectural Decisions (CTO):",
            getattr(state.cto_output, "architecture", "None provided") if state.cto_output else "None provided",
            "",
            "Enriched Brief with Acceptance Criteria (Team Leader):",
        ]
        for ac in state.acceptance_criteria or []:
            lines.append(f"- {ac}")
            
        return "\n".join(lines)
