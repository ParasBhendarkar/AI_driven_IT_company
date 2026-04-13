from __future__ import annotations

import json
import logging
import time

from agent.base import BaseAgent
from models.schemas import TaskState, TaskStatus, CriticOutput

logger = logging.getLogger(__name__)


class CriticAgent(BaseAgent):
    role = "Critic"
    model = "claude-sonnet-4-5"

    SYSTEM_PROMPT = """
You are an expert root-cause analyst for a software development system.
You receive the full attempt history for a failing task: all QA failure reports,
all error messages, and the last developer diff or file changes.

Your job: identify the REAL underlying bug, not the surface symptoms.
Think carefully about WHY the same test keeps failing across multiple attempts.

Respond ONLY with valid JSON — no prose, no markdown:
{
  "root_cause": "one clear sentence describing the real underlying problem",
  "fix": "exact code change or approach needed to fix it",
  "confidence": 0.0,
  "additional_concerns": ["any other issues you spotted"]
}

confidence is 0.0 to 1.0. Be honest — low confidence means more human review needed.
"""

    async def run(self, state: TaskState) -> TaskState:
        start = time.time()
        await self._publish(
            state.task_id,
            f"Analysing failure pattern across {state.retry_count} attempts...",
        )

        prompt = self._build_prompt(state)
        messages = [{"role": "user", "content": prompt}]

        response = await self._call_llm(
            messages=messages,
            system=self.SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1024,
        )

        tokens = response.usage.total_tokens if response.usage else 0
        content = response.choices[0].message.content or "{}"
        latency = time.time() - start

        critic_output = _parse_critic_response(content, state.task_id)
        state.critic_output = critic_output

        await self._publish(
            state.task_id,
            f"Root cause identified: {critic_output.root_cause or critic_output.summary}",
            event_type="warning",
            payload=critic_output.model_dump(),
        )

        await self._log_call(
            task_id=state.task_id,
            action="critic_analysis",
            input_payload={"attempt_count": state.retry_count},
            output_payload=critic_output.model_dump(),
            tokens_used=tokens,
            latency_seconds=latency,
        )

        return state

    def _build_prompt(self, state: TaskState) -> str:
        lines = [
            f"Task: {state.title}",
            f"Total attempts so far: {state.retry_count}",
            "",
            "=== ERROR HISTORY ===",
        ]

        for i, err in enumerate(state.error_history or [], 1):
            lines.append(f"Attempt {i}: {err}")

        if state.qa_result:
            lines.append("")
            lines.append("=== LATEST QA FAILURES ===")
            for f in (state.qa_result.failures or []):
                lines.append(f"- {f.name}: {f.error}")

        if state.dev_output:
            lines.append("")
            lines.append("=== LAST DEV CHANGES ===")
            for fc in (state.dev_output.files_changed or []):
                lines.append(f"- {fc.file_path}: {fc.summary}")

        lines.append("")
        lines.append("Identify the root cause and provide a specific fix.")
        return "\n".join(lines)


def _parse_critic_response(content: str, task_id: str) -> CriticOutput:
    """Parse JSON from Critic LLM response into CriticOutput."""
    clean = content.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.strip()

    try:
        data = json.loads(clean)
        return CriticOutput(
            score=data.get("confidence", 0.5) * 10,
            summary=data.get("root_cause", "Unknown root cause"),
            root_cause=data.get("root_cause"),
            fix=data.get("fix"),
            confidence=data.get("confidence"),
            recommendation=data.get("fix"),
            approved=data.get("confidence", 0) >= 0.8,
        )
    except (json.JSONDecodeError, Exception) as exc:
        logger.warning("Critic JSON parse failed: %s — raw: %s", exc, content[:200])
        return CriticOutput(
            score=3.0,
            summary=content[:500] if content else "Critic analysis failed",
            root_cause=None,
            fix=None,
            confidence=None,
            recommendation=None,
            approved=False,
        )
